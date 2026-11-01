"""Relational model for the house.

Money and weight are decimals. Names on an order line are copied at sale time
so a later rename does not rewrite history.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UtcDateTime, UUIDPrimaryKey, utcnow


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="clerk", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class RefreshToken(UUIDPrimaryKey, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_tokens", lazy="raise")


class ApiKey(UUIDPrimaryKey, Base):
    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys", lazy="raise")


class IdempotencyKey(UUIDPrimaryKey, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Supplier(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(160), unique=True)
    region: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    fruits: Mapped[list["Fruit"]] = relationship(back_populates="supplier", lazy="raise")


class Fruit(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "fruits"
    __table_args__ = (CheckConstraint("price_per_kg > 0", name="ck_fruit_price_positive"),)

    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    origin: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False)
    season_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    supplier: Mapped[Supplier | None] = relationship(back_populates="fruits", lazy="raise")
    lots: Mapped[list["StockLot"]] = relationship(back_populates="fruit", lazy="raise")


class StockLot(UUIDPrimaryKey, Base):
    __tablename__ = "stock_lots"
    __table_args__ = (CheckConstraint("quantity_kg >= 0", name="ck_lot_qty_nonneg"),)

    fruit_id: Mapped[str] = mapped_column(ForeignKey("fruits.id", ondelete="CASCADE"), index=True)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    warehouse: Mapped[str] = mapped_column(String(80), default="Cold room A")
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    fruit: Mapped[Fruit] = relationship(back_populates="lots", lazy="raise")


class Order(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "orders"

    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class OrderLine(UUIDPrimaryKey, Base):
    __tablename__ = "order_lines"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_line_qty_positive"),)

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    fruit_id: Mapped[str] = mapped_column(ForeignKey("fruits.id", ondelete="RESTRICT"), index=True)
    fruit_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(40))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped[Order] = relationship(back_populates="lines", lazy="raise")


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"

    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, index=True)
