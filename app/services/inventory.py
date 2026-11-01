"""Stock lots. Sales and negative adjustments draw down the oldest lot first."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Conflict, NotFound
from app.models import Fruit, StockLot
from app.schemas.catalog import StockLotOut


async def on_hand(session: AsyncSession, fruit_id: str) -> Decimal:
    lots = (
        await session.scalars(select(StockLot).where(StockLot.fruit_id == fruit_id, StockLot.quantity_kg > 0))
    ).all()
    return sum((lot.quantity_kg for lot in lots), Decimal("0"))


async def consume(session: AsyncSession, fruit_id: str, quantity: Decimal) -> None:
    if quantity <= 0:
        raise Conflict("Quantity must be positive.")
    lots = (
        await session.scalars(
            select(StockLot)
            .where(StockLot.fruit_id == fruit_id, StockLot.quantity_kg > 0)
            .order_by(StockLot.received_at.asc(), StockLot.id.asc())
        )
    ).all()
    remaining = quantity
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.quantity_kg, remaining)
        lot.quantity_kg = lot.quantity_kg - take
        remaining -= take
        if lot.quantity_kg == 0:
            await session.delete(lot)
    if remaining > 0:
        raise Conflict(f"Not enough stock. Short by {format(remaining, 'f')} kg.")


async def receive(
    session: AsyncSession,
    *,
    fruit_id: str,
    quantity_kg: Decimal,
    unit_cost: Decimal,
    warehouse: str,
    expires_on,
    note: str | None,
) -> StockLot:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None or fruit.archived_at is not None:
        raise NotFound("Fruit not found.")
    lot = StockLot(
        fruit_id=fruit.id,
        quantity_kg=quantity_kg,
        unit_cost=unit_cost,
        warehouse=warehouse,
        expires_on=expires_on,
        note=note,
        received_at=datetime.now(UTC),
    )
    session.add(lot)
    await session.flush()
    return lot


async def adjust(session: AsyncSession, *, fruit_id: str, quantity_kg: Decimal, reason: str) -> Decimal:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None or fruit.archived_at is not None:
        raise NotFound("Fruit not found.")
    if quantity_kg > 0:
        await receive(
            session,
            fruit_id=fruit_id,
            quantity_kg=quantity_kg,
            unit_cost=Decimal("0"),
            warehouse="Adjustment",
            expires_on=None,
            note=reason,
        )
    else:
        await consume(session, fruit_id, abs(quantity_kg))
    return await on_hand(session, fruit_id)


async def restore(session: AsyncSession, *, fruit_id: str, quantity_kg: Decimal, note: str) -> None:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None:
        return
    session.add(
        StockLot(
            fruit_id=fruit_id,
            quantity_kg=quantity_kg,
            unit_cost=Decimal("0"),
            warehouse="Returns",
            note=note,
            received_at=datetime.now(UTC),
        )
    )
    await session.flush()


def lot_out(lot: StockLot, fruit: Fruit | None) -> StockLotOut:
    return StockLotOut(
        id=lot.id,
        fruit_id=lot.fruit_id,
        fruit_name=fruit.name if fruit else None,
        sku=fruit.sku if fruit else None,
        quantity_kg=lot.quantity_kg,
        unit_cost=lot.unit_cost,
        warehouse=lot.warehouse,
        received_at=lot.received_at,
        expires_on=lot.expires_on,
        note=lot.note,
    )


async def list_lots(session: AsyncSession, fruit_id: str | None) -> list[StockLotOut]:
    stmt = select(StockLot).where(StockLot.quantity_kg > 0).order_by(StockLot.received_at.desc())
    if fruit_id:
        stmt = stmt.where(StockLot.fruit_id == fruit_id)
    lots = list((await session.scalars(stmt)).all())
    fruits = {}
    if lots:
        rows = (
            await session.scalars(select(Fruit).where(Fruit.id.in_({lot.fruit_id for lot in lots})))
        ).all()
        fruits = {row.id: row for row in rows}
    return [lot_out(lot, fruits.get(lot.fruit_id)) for lot in lots]
