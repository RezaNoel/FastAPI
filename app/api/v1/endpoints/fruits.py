"""Produce catalog.

Reads are public so the floor board can render before anyone signs in.
Writes require `catalog:write`. Updates honor `If-Match`.
"""

import csv
import io
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response, Security
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession, get_principal
from app.core.config import get_settings
from app.models import Fruit, User
from app.schemas.catalog import FruitCreate, FruitFilters, FruitOut, FruitUpdate
from app.schemas.common import PROBLEMS, Page
from app.services import audit, catalog

router = APIRouter(responses=PROBLEMS)


def _threshold() -> Decimal:
    return Decimal(str(get_settings().low_stock_kg))


@router.get("", response_model=Page[FruitOut], operation_id="listFruits")
async def list_fruits(
    session: DbSession,
    response: Response,
    filters: Annotated[FruitFilters, Query()],
) -> Page[FruitOut]:
    response.headers["Cache-Control"] = "public, max-age=5"
    return await catalog.list_fruits(
        session,
        filters,
        page=filters.page,
        size=filters.size,
        threshold=_threshold(),
    )


@router.get("/export", operation_id="exportFruits")
async def export_fruits(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["catalog:read"])],
) -> StreamingResponse:
    rows = list(
        (
            await session.scalars(select(Fruit).where(Fruit.archived_at.is_(None)).order_by(Fruit.name.asc()))
        ).all()
    )

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["sku", "name", "category", "origin", "price_per_kg", "seasonal", "season"])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for fruit in rows:
            writer.writerow(
                [
                    fruit.sku,
                    fruit.name,
                    fruit.category,
                    fruit.origin,
                    f"{fruit.price_per_kg:.2f}",
                    "yes" if fruit.is_seasonal else "no",
                    fruit.season_label or "",
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    headers = {"Content-Disposition": 'attachment; filename="grove-catalog.csv"'}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


@router.get("/{fruit_id}", response_model=FruitOut, operation_id="getFruit")
async def get_fruit(fruit_id: str, request: Request, response: Response, session: DbSession):
    fruit = await catalog.get_fruit(session, fruit_id, _threshold())
    etag = f'"{fruit.version}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=5"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return fruit


@router.post("", response_model=FruitOut, status_code=201, operation_id="createFruit")
async def create_fruit(
    payload: FruitCreate,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["catalog:write"])],
) -> FruitOut:
    fruit = await catalog.create_fruit(session, payload.model_dump(), _threshold())
    await audit.record(
        session,
        actor_id=user.id,
        action="fruit.created",
        entity="fruit",
        entity_id=fruit.id,
        detail={"sku": fruit.sku},
    )
    return fruit


@router.patch("/{fruit_id}", response_model=FruitOut, operation_id="updateFruit")
async def update_fruit(
    fruit_id: str,
    payload: FruitUpdate,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["catalog:write"])],
    if_match: Annotated[str | None, Header()] = None,
) -> FruitOut:
    fruit = await catalog.update_fruit(
        session,
        fruit_id,
        payload.changed(),
        if_match=if_match,
        threshold=_threshold(),
    )
    await audit.record(
        session,
        actor_id=user.id,
        action="fruit.updated",
        entity="fruit",
        entity_id=fruit.id,
        detail={"version": fruit.version},
    )
    return fruit


@router.delete("/{fruit_id}", status_code=204, operation_id="archiveFruit")
async def archive_fruit(
    fruit_id: str,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["catalog:write"])],
) -> None:
    fruit = await catalog.archive_fruit(session, fruit_id)
    await audit.record(
        session,
        actor_id=user.id,
        action="fruit.archived",
        entity="fruit",
        entity_id=fruit.id,
        detail={"sku": fruit.sku},
    )
