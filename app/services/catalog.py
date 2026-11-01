"""Catalog and grower queries."""

import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Conflict, NotFound, PreconditionFailed
from app.models import Fruit, StockLot, Supplier
from app.schemas.catalog import FruitFilters, FruitOut, SupplierOut
from app.schemas.common import Page


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def stock_status(quantity: Decimal, threshold: Decimal) -> str:
    if quantity <= 0:
        return "out"
    if quantity < threshold:
        return "low"
    return "ok"


def fruit_out(
    fruit: Fruit,
    quantity: Decimal,
    *,
    supplier_name: str | None,
    threshold: Decimal,
) -> FruitOut:
    image = f"/media/{fruit.image_path}" if fruit.image_path else None
    return FruitOut(
        id=fruit.id,
        sku=fruit.sku,
        name=fruit.name,
        category=fruit.category,
        origin=fruit.origin,
        description=fruit.description,
        price_per_kg=fruit.price_per_kg,
        is_seasonal=fruit.is_seasonal,
        season_label=fruit.season_label,
        image_url=image,
        version=fruit.version,
        supplier_id=fruit.supplier_id,
        supplier_name=supplier_name,
        quantity_on_hand=quantity,
        stock_status=stock_status(quantity, threshold),
        created_at=fruit.created_at,
        updated_at=fruit.updated_at,
    )


def _apply_filters(stmt, filters: FruitFilters):
    stmt = stmt.where(Fruit.archived_at.is_(None))
    if filters.category:
        stmt = stmt.where(Fruit.category == filters.category)
    if filters.origin:
        stmt = stmt.where(Fruit.origin.ilike(like_pattern(filters.origin), escape="\\"))
    if filters.seasonal is not None:
        stmt = stmt.where(Fruit.is_seasonal.is_(filters.seasonal))
    if filters.min_price is not None:
        stmt = stmt.where(Fruit.price_per_kg >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Fruit.price_per_kg <= filters.max_price)
    if filters.q:
        pattern = like_pattern(filters.q.strip())
        stmt = stmt.where(
            or_(
                Fruit.name.ilike(pattern, escape="\\"),
                Fruit.sku.ilike(pattern, escape="\\"),
                Fruit.origin.ilike(pattern, escape="\\"),
            )
        )
    return stmt


_SORTS = {
    "name": Fruit.name.asc(),
    "-name": Fruit.name.desc(),
    "price": Fruit.price_per_kg.asc(),
    "-price": Fruit.price_per_kg.desc(),
    "newest": Fruit.created_at.desc(),
}


async def quantities_for(session: AsyncSession, fruit_ids: list[str]) -> dict[str, Decimal]:
    if not fruit_ids:
        return {}
    rows = (
        await session.execute(
            select(StockLot.fruit_id, func.coalesce(func.sum(StockLot.quantity_kg), 0))
            .where(StockLot.fruit_id.in_(fruit_ids))
            .group_by(StockLot.fruit_id)
        )
    ).all()
    return {fruit_id: Decimal(qty) for fruit_id, qty in rows}


async def supplier_names(session: AsyncSession, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (await session.scalars(select(Supplier).where(Supplier.id.in_(ids)))).all()
    return {row.id: row.name for row in rows}


async def list_fruits(
    session: AsyncSession,
    filters: FruitFilters,
    *,
    page: int,
    size: int,
    threshold: Decimal,
) -> Page[FruitOut]:
    filtered = _apply_filters(select(Fruit), filters)
    total = int(await session.scalar(_apply_filters(select(func.count()).select_from(Fruit), filters)) or 0)
    stmt = filtered.order_by(_SORTS[filters.sort]).offset((page - 1) * size).limit(size)
    fruits = list((await session.scalars(stmt)).all())
    qty = await quantities_for(session, [fruit.id for fruit in fruits])
    names = await supplier_names(session, [fruit.supplier_id for fruit in fruits if fruit.supplier_id])
    items = [
        fruit_out(
            fruit,
            qty.get(fruit.id, Decimal("0")),
            supplier_name=names.get(fruit.supplier_id or ""),
            threshold=threshold,
        )
        for fruit in fruits
    ]
    pages = math.ceil(total / size) if total else 0
    return Page(items=items, total=total, page=page, size=size, pages=pages)


async def get_fruit(session: AsyncSession, fruit_id: str, threshold: Decimal) -> FruitOut:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None:
        raise NotFound("Fruit not found.")
    qty = await quantities_for(session, [fruit.id])
    names = await supplier_names(session, [fruit.supplier_id] if fruit.supplier_id else [])
    return fruit_out(
        fruit,
        qty.get(fruit.id, Decimal("0")),
        supplier_name=names.get(fruit.supplier_id or ""),
        threshold=threshold,
    )


async def create_fruit(session: AsyncSession, data: dict, threshold: Decimal) -> FruitOut:
    if data.get("supplier_id"):
        supplier = await session.get(Supplier, data["supplier_id"])
        if supplier is None or not supplier.is_active:
            raise NotFound("Supplier not found.")
    fruit = Fruit(**data)
    session.add(fruit)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("A fruit with this SKU already exists.") from exc
    return await get_fruit(session, fruit.id, threshold)


async def update_fruit(
    session: AsyncSession,
    fruit_id: str,
    changes: dict,
    *,
    if_match: str | None,
    threshold: Decimal,
) -> FruitOut:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None or fruit.archived_at is not None:
        raise NotFound("Fruit not found.")
    if not changes:
        raise Conflict("No fields to update.")
    if if_match is not None and if_match.strip().strip('"') != str(fruit.version):
        raise PreconditionFailed("The catalog row changed. Reload it and try again.")
    if "supplier_id" in changes and changes["supplier_id"]:
        supplier = await session.get(Supplier, changes["supplier_id"])
        if supplier is None or not supplier.is_active:
            raise NotFound("Supplier not found.")
    for key, value in changes.items():
        setattr(fruit, key, value)
    fruit.version += 1
    fruit.updated_at = datetime.now(UTC)
    await session.flush()
    return await get_fruit(session, fruit.id, threshold)


async def archive_fruit(session: AsyncSession, fruit_id: str) -> Fruit:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None or fruit.archived_at is not None:
        raise NotFound("Fruit not found.")
    fruit.archived_at = datetime.now(UTC)
    fruit.updated_at = datetime.now(UTC)
    fruit.version += 1
    await session.flush()
    return fruit


async def iter_fruit_rows(session: AsyncSession):
    stmt = select(Fruit).where(Fruit.archived_at.is_(None)).order_by(Fruit.name.asc())
    for fruit in (await session.scalars(stmt)).all():
        yield fruit


def supplier_out(supplier: Supplier, fruit_count: int) -> SupplierOut:
    return SupplierOut(
        id=supplier.id,
        name=supplier.name,
        region=supplier.region,
        contact_email=supplier.contact_email,
        phone=supplier.phone,
        notes=supplier.notes,
        is_active=supplier.is_active,
        fruit_count=fruit_count,
        created_at=supplier.created_at,
    )


async def list_suppliers(session: AsyncSession, *, page: int, size: int, q: str | None) -> Page[SupplierOut]:
    stmt = select(Supplier)
    count_stmt = select(func.count()).select_from(Supplier)
    if q:
        pattern = Supplier.name.ilike(like_pattern(q.strip()), escape="\\")
        stmt = stmt.where(pattern)
        count_stmt = count_stmt.where(pattern)
    total = int(await session.scalar(count_stmt) or 0)
    rows = list(
        (
            await session.scalars(stmt.order_by(Supplier.name.asc()).offset((page - 1) * size).limit(size))
        ).all()
    )
    counts: dict[str, int] = {}
    if rows:
        counted = (
            await session.execute(
                select(Fruit.supplier_id, func.count())
                .where(Fruit.supplier_id.in_([row.id for row in rows]), Fruit.archived_at.is_(None))
                .group_by(Fruit.supplier_id)
            )
        ).all()
        counts = {supplier_id: int(count) for supplier_id, count in counted}
    items = [supplier_out(row, counts.get(row.id, 0)) for row in rows]
    pages = math.ceil(total / size) if total else 0
    return Page(items=items, total=total, page=page, size=size, pages=pages)


async def create_supplier(session: AsyncSession, data: dict) -> SupplierOut:
    supplier = Supplier(**data)
    session.add(supplier)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("A grower with this name already exists.") from exc
    return supplier_out(supplier, 0)


async def update_supplier(session: AsyncSession, supplier_id: str, changes: dict) -> SupplierOut:
    supplier = await session.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound("Supplier not found.")
    if not changes:
        raise Conflict("No fields to update.")
    for key, value in changes.items():
        setattr(supplier, key, value)
    supplier.updated_at = datetime.now(UTC)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("A grower with this name already exists.") from exc
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(Fruit)
            .where(
                Fruit.supplier_id == supplier.id,
                Fruit.archived_at.is_(None),
            )
        )
        or 0
    )
    return supplier_out(supplier, count)
