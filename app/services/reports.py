"""Floor summary used by the opening screen."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import Fruit, Order, StockLot
from app.schemas.commerce import CategoryStock, LowStockItem, SummaryOut
from app.services.orders import order_out


async def summary(session: AsyncSession) -> SummaryOut:
    settings = get_settings()
    threshold = Decimal(str(settings.low_stock_kg))
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    sku_count = int(
        await session.scalar(select(func.count()).select_from(Fruit).where(Fruit.archived_at.is_(None))) or 0
    )
    stock_kg = Decimal(
        str(await session.scalar(select(func.coalesce(func.sum(StockLot.quantity_kg), 0))) or 0)
    )
    open_orders = int(
        await session.scalar(select(func.count()).select_from(Order).where(Order.status == "confirmed")) or 0
    )
    revenue = Decimal(
        str(
            await session.scalar(
                select(func.coalesce(func.sum(Order.total), 0)).where(
                    Order.created_at >= start,
                    Order.status.in_(("confirmed", "fulfilled")),
                )
            )
            or 0
        )
    )

    qty = func.coalesce(func.sum(StockLot.quantity_kg), 0)
    low_rows = (
        await session.execute(
            select(Fruit, qty.label("qty"))
            .outerjoin(StockLot, StockLot.fruit_id == Fruit.id)
            .where(Fruit.archived_at.is_(None))
            .group_by(Fruit.id)
            .having(qty < threshold)
            .order_by(qty.asc())
        )
    ).all()
    low_stock = [
        LowStockItem(
            id=fruit.id,
            sku=fruit.sku,
            name=fruit.name,
            category=fruit.category,
            quantity_kg=Decimal(str(amount)),
        )
        for fruit, amount in low_rows
    ]

    category_rows = (
        await session.execute(
            select(Fruit.category, func.coalesce(func.sum(StockLot.quantity_kg), 0))
            .outerjoin(StockLot, StockLot.fruit_id == Fruit.id)
            .where(Fruit.archived_at.is_(None))
            .group_by(Fruit.category)
            .order_by(Fruit.category.asc())
        )
    ).all()
    categories = [
        CategoryStock(category=category, quantity_kg=Decimal(str(amount)))
        for category, amount in category_rows
    ]

    recent = (
        await session.scalars(
            select(Order).options(selectinload(Order.lines)).order_by(Order.created_at.desc()).limit(6)
        )
    ).all()

    return SummaryOut(
        sku_count=sku_count,
        stock_kg=stock_kg,
        open_orders=open_orders,
        revenue_today=revenue,
        low_stock=low_stock,
        categories=categories,
        recent_orders=[order_out(order) for order in recent],
    )
