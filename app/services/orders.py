"""Orders commit stock immediately. Cancelling puts it back in Returns."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.problems import Conflict, NotFound
from app.models import Fruit, Order, OrderLine, User
from app.schemas.commerce import OrderCreate, OrderOut
from app.services import audit, inventory
from app.services.events import hub

logger = logging.getLogger("grove.orders")


def order_out(order: Order) -> OrderOut:
    return OrderOut.model_validate(order)


async def _load(session: AsyncSession, order_id: str) -> Order:
    stmt = select(Order).options(selectinload(Order.lines)).where(Order.id == order_id)
    order = await session.scalar(stmt)
    if order is None:
        raise NotFound("Order not found.")
    return order


async def _next_number(session: AsyncSession) -> str:
    count = int(await session.scalar(select(func.count()).select_from(Order)) or 0)
    return f"GRV-{1001 + count}"


async def create_order(
    session: AsyncSession,
    payload: OrderCreate,
    actor: User,
    *,
    announce: bool = True,
) -> OrderOut:
    fruits: dict[str, Fruit] = {}
    for line in payload.lines:
        fruit = await session.get(Fruit, line.fruit_id)
        if fruit is None or fruit.archived_at is not None:
            raise NotFound(f"Fruit {line.fruit_id} is not in the catalog.")
        fruits[fruit.id] = fruit

    # Draw stock before inserting the order so a short lot aborts the whole sale.
    for line in payload.lines:
        await inventory.consume(session, line.fruit_id, line.quantity_kg)

    total = Decimal("0")
    order = Order(
        number=await _next_number(session),
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        notes=payload.notes,
        status="confirmed",
        total=Decimal("0"),
        created_by=actor.id,
    )
    session.add(order)
    await session.flush()

    for line in payload.lines:
        fruit = fruits[line.fruit_id]
        extended = (fruit.price_per_kg * line.quantity_kg).quantize(Decimal("0.01"))
        total += extended
        session.add(
            OrderLine(
                order_id=order.id,
                fruit_id=fruit.id,
                fruit_name=fruit.name,
                sku=fruit.sku,
                quantity_kg=line.quantity_kg,
                unit_price=fruit.price_per_kg,
                line_total=extended,
            )
        )
    order.total = total
    await session.flush()
    await audit.record(
        session,
        actor_id=actor.id,
        action="order.created",
        entity="order",
        entity_id=order.id,
        detail={"number": order.number, "total": str(total)},
    )
    stored = await _load(session, order.id)
    result = order_out(stored)
    if announce:
        await hub.publish(
            "order.created",
            {
                "number": result.number,
                "customer": result.customer_name,
                "total": float(result.total),
            },
        )
    return result


async def list_orders(session: AsyncSession, *, page: int, size: int, status: str | None):
    import math

    from app.schemas.common import Page

    stmt = select(Order).options(selectinload(Order.lines))
    count_stmt = select(func.count()).select_from(Order)
    if status:
        stmt = stmt.where(Order.status == status)
        count_stmt = count_stmt.where(Order.status == status)
    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        await session.scalars(stmt.order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    pages = math.ceil(total / size) if total else 0
    return Page(items=[order_out(row) for row in rows], total=total, page=page, size=size, pages=pages)


async def get_order(session: AsyncSession, order_id: str) -> OrderOut:
    return order_out(await _load(session, order_id))


async def cancel_order(session: AsyncSession, order_id: str, actor: User) -> OrderOut:
    order = await _load(session, order_id)
    if order.status != "confirmed":
        raise Conflict(f"A {order.status} order cannot be cancelled.")
    for line in order.lines:
        await inventory.restore(
            session,
            fruit_id=line.fruit_id,
            quantity_kg=line.quantity_kg,
            note=f"Returned from {order.number}",
        )
    order.status = "cancelled"
    order.updated_at = datetime.now(UTC)
    await audit.record(
        session,
        actor_id=actor.id,
        action="order.cancelled",
        entity="order",
        entity_id=order.id,
        detail={"number": order.number},
    )
    await session.flush()
    await hub.publish("order.cancelled", {"number": order.number, "customer": order.customer_name})
    return order_out(order)


async def fulfill_order(session: AsyncSession, order_id: str, actor: User) -> OrderOut:
    order = await _load(session, order_id)
    if order.status != "confirmed":
        raise Conflict(f"A {order.status} order cannot be fulfilled.")
    order.status = "fulfilled"
    order.updated_at = datetime.now(UTC)
    await audit.record(
        session,
        actor_id=actor.id,
        action="order.fulfilled",
        entity="order",
        entity_id=order.id,
        detail={"number": order.number},
    )
    await session.flush()
    await hub.publish("order.fulfilled", {"number": order.number, "customer": order.customer_name})
    return order_out(order)


def write_receipt(order_number: str, customer: str, total: str) -> None:
    """Background task. Runs after the response, without the request session."""
    settings = get_settings()
    path = settings.media_path / "receipts.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {order_number} {customer} {total}\n")
    logger.info("receipt written for %s", order_number)
