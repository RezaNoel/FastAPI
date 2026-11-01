"""Receipts, adjustments, and the lots currently on the floor."""

from typing import Annotated

from fastapi import APIRouter, Query, Security

from app.api.deps import DbSession, get_principal
from app.models import User
from app.schemas.catalog import AdjustmentIn, ReceiptIn, StockLotOut
from app.schemas.common import PROBLEMS
from app.services import audit, inventory

router = APIRouter(responses=PROBLEMS)


@router.get("/lots", response_model=list[StockLotOut], operation_id="listLots")
async def list_lots(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["inventory:read"])],
    fruit_id: str | None = Query(default=None),
) -> list[StockLotOut]:
    return await inventory.list_lots(session, fruit_id)


@router.post("/receipts", response_model=StockLotOut, status_code=201, operation_id="receiveStock")
async def receive_stock(
    payload: ReceiptIn,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["inventory:write"])],
) -> StockLotOut:
    lot = await inventory.receive(session, **payload.model_dump())
    await audit.record(
        session,
        actor_id=user.id,
        action="stock.received",
        entity="fruit",
        entity_id=lot.fruit_id,
        detail={"quantity_kg": str(lot.quantity_kg), "warehouse": lot.warehouse},
    )
    rows = await inventory.list_lots(session, lot.fruit_id)
    match = next(row for row in rows if row.id == lot.id)
    return match


@router.post("/adjustments", operation_id="adjustStock")
async def adjust_stock(
    payload: AdjustmentIn,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["inventory:write"])],
) -> dict:
    remaining = await inventory.adjust(session, **payload.model_dump())
    await audit.record(
        session,
        actor_id=user.id,
        action="stock.adjusted",
        entity="fruit",
        entity_id=payload.fruit_id,
        detail={"quantity_kg": str(payload.quantity_kg), "reason": payload.reason},
    )
    return {"fruit_id": payload.fruit_id, "quantity_on_hand": float(remaining)}
