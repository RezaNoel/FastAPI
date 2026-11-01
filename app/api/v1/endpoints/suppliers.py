"""Growers who supply the house."""

from typing import Annotated

from fastapi import APIRouter, Query, Security

from app.api.deps import DbSession, get_principal
from app.models import User
from app.schemas.catalog import SupplierCreate, SupplierOut, SupplierUpdate
from app.schemas.common import PROBLEMS, Page
from app.services import audit, catalog

router = APIRouter(responses=PROBLEMS)


@router.get("", response_model=Page[SupplierOut], operation_id="listSuppliers")
async def list_suppliers(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["suppliers:read"])],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    q: str | None = Query(default=None, max_length=80),
) -> Page[SupplierOut]:
    return await catalog.list_suppliers(session, page=page, size=size, q=q)


@router.post("", response_model=SupplierOut, status_code=201, operation_id="createSupplier")
async def create_supplier(
    payload: SupplierCreate,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["suppliers:write"])],
) -> SupplierOut:
    supplier = await catalog.create_supplier(session, payload.model_dump())
    await audit.record(
        session,
        actor_id=user.id,
        action="supplier.created",
        entity="supplier",
        entity_id=supplier.id,
        detail={"name": supplier.name},
    )
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut, operation_id="updateSupplier")
async def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["suppliers:write"])],
) -> SupplierOut:
    supplier = await catalog.update_supplier(session, supplier_id, payload.changed())
    await audit.record(
        session,
        actor_id=user.id,
        action="supplier.updated",
        entity="supplier",
        entity_id=supplier.id,
        detail={"name": supplier.name},
    )
    return supplier
