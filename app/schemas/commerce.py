"""Orders, reports, and audit contracts."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import Money, ORMModel, Quantity


class OrderLineIn(BaseModel):
    fruit_id: str
    quantity_kg: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=3)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=500)
    lines: list[OrderLineIn] = Field(min_length=1, max_length=40)

    @field_validator("customer_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def _unique_fruits(self) -> "OrderCreate":
        seen: set[str] = set()
        for line in self.lines:
            if line.fruit_id in seen:
                raise ValueError("Each fruit can appear once on an order; combine the weight")
            seen.add(line.fruit_id)
        return self


class OrderLineOut(ORMModel):
    id: str
    fruit_id: str
    fruit_name: str
    sku: str
    quantity_kg: Quantity
    unit_price: Money
    line_total: Money


class OrderOut(ORMModel):
    id: str
    number: str
    customer_name: str
    customer_email: str | None
    status: str
    notes: str | None
    total: Money
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[OrderLineOut]


class CategoryStock(BaseModel):
    category: str
    quantity_kg: Quantity


class LowStockItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    quantity_kg: Quantity


class SummaryOut(BaseModel):
    sku_count: int
    stock_kg: Quantity
    open_orders: int
    revenue_today: Money
    low_stock: list[LowStockItem]
    categories: list[CategoryStock]
    recent_orders: list[OrderOut]


class AuditOut(ORMModel):
    id: str
    actor_id: str | None
    actor_name: str | None = None
    action: str
    entity: str
    entity_id: str
    detail: str | None
    created_at: datetime
