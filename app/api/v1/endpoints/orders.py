"""Orders. A confirmed order has already drawn stock."""

import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Query, Security, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import DbSession, get_principal
from app.core.problems import Conflict, Unprocessable
from app.core.security import sha256
from app.models import IdempotencyKey, User
from app.schemas.commerce import OrderCreate, OrderOut
from app.schemas.common import PROBLEMS, Page
from app.services import orders

router = APIRouter(responses=PROBLEMS)


@router.get("", response_model=Page[OrderOut], operation_id="listOrders")
async def list_orders(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["orders:read"])],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page[OrderOut]:
    if status_filter and status_filter not in {"confirmed", "fulfilled", "cancelled"}:
        raise Unprocessable("Status must be confirmed, fulfilled, or cancelled.")
    return await orders.list_orders(session, page=page, size=size, status=status_filter)


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="createOrder")
async def create_order(
    payload: OrderCreate,
    session: DbSession,
    background: BackgroundTasks,
    user: Annotated[User, Security(get_principal, scopes=["orders:write"])],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    """Open an order.

    Send `Idempotency-Key` when the client might retry. The same key and body
    replay the original response and do not draw stock twice. A reused key with
    a different body is a conflict.
    """
    digest = sha256(payload.model_dump_json())
    if idempotency_key is not None:
        if len(idempotency_key) > 80:
            raise Unprocessable("Idempotency-Key must be 80 characters or fewer.")
        existing = await session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != digest:
                raise Conflict("This idempotency key was already used with a different request.")
            return JSONResponse(
                content=json.loads(existing.response_body),
                status_code=existing.status_code,
                headers={"Idempotent-Replayed": "true"},
            )

    order = await orders.create_order(session, payload, user)
    body = order.model_dump(mode="json")
    if idempotency_key is not None:
        session.add(
            IdempotencyKey(
                user_id=user.id,
                key=idempotency_key,
                request_hash=digest,
                status_code=201,
                response_body=json.dumps(body),
            )
        )
        await session.flush()
    background.add_task(orders.write_receipt, order.number, order.customer_name, f"{order.total:.2f}")
    return order


@router.get("/{order_id}", response_model=OrderOut, operation_id="getOrder")
async def get_order(
    order_id: str,
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["orders:read"])],
) -> OrderOut:
    return await orders.get_order(session, order_id)


@router.post("/{order_id}/cancel", response_model=OrderOut, operation_id="cancelOrder")
async def cancel_order(
    order_id: str,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["orders:write"])],
) -> OrderOut:
    return await orders.cancel_order(session, order_id, user)


@router.post("/{order_id}/fulfill", response_model=OrderOut, operation_id="fulfillOrder")
async def fulfill_order(
    order_id: str,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["orders:fulfill"])],
) -> OrderOut:
    return await orders.fulfill_order(session, order_id, user)
