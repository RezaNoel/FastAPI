"""Catalog, growers, and stock contracts."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import Money, ORMModel, Quantity

CATEGORIES = ("citrus", "berry", "tropical", "stone", "pome", "melon", "other")
Category = Literal["citrus", "berry", "tropical", "stone", "pome", "melon", "other"]
FruitSort = Literal["name", "-name", "price", "-price", "newest"]


class FruitFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=80)
    category: Category | None = None
    origin: str | None = Field(default=None, max_length=120)
    seasonal: bool | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    sort: FruitSort = "name"
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class FruitCreate(BaseModel):
    sku: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    category: Category
    origin: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    price_per_kg: Decimal = Field(gt=0, le=100000, max_digits=12, decimal_places=2)
    is_seasonal: bool = False
    season_label: str | None = Field(default=None, max_length=80)
    supplier_id: str | None = None

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{3,40}", value):
            raise ValueError("SKU must be 3–40 characters: A–Z, 0–9, hyphen")
        return value

    @field_validator("name", "origin")
    @classmethod
    def _text(cls, value: str) -> str:
        return " ".join(value.split())


class FruitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    category: Category | None = None
    origin: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_per_kg: Decimal | None = Field(default=None, gt=0, le=100000, max_digits=12, decimal_places=2)
    is_seasonal: bool | None = None
    season_label: str | None = Field(default=None, max_length=80)
    supplier_id: str | None = None

    def changed(self) -> dict:
        return self.model_dump(exclude_unset=True)


class FruitOut(ORMModel):
    id: str
    sku: str
    name: str
    category: str
    origin: str
    description: str
    price_per_kg: Money
    is_seasonal: bool
    season_label: str | None
    image_url: str | None = None
    version: int
    supplier_id: str | None
    supplier_name: str | None = None
    quantity_on_hand: Quantity = Decimal("0")
    stock_status: str = "ok"
    created_at: datetime
    updated_at: datetime


class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    region: str = Field(min_length=2, max_length=120)
    contact_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "region")
    @classmethod
    def _text(cls, value: str) -> str:
        return " ".join(value.split())


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    region: str | None = Field(default=None, min_length=2, max_length=120)
    contact_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    def changed(self) -> dict:
        return self.model_dump(exclude_unset=True)


class SupplierOut(ORMModel):
    id: str
    name: str
    region: str
    contact_email: str | None
    phone: str | None
    notes: str | None
    is_active: bool
    fruit_count: int = 0
    created_at: datetime


class ReceiptIn(BaseModel):
    fruit_id: str
    quantity_kg: Decimal = Field(gt=0, le=100000, max_digits=12, decimal_places=3)
    unit_cost: Decimal = Field(ge=0, le=100000, max_digits=12, decimal_places=2)
    warehouse: str = Field(default="Cold room A", min_length=2, max_length=80)
    expires_on: date | None = None
    note: str | None = Field(default=None, max_length=200)


class AdjustmentIn(BaseModel):
    fruit_id: str
    quantity_kg: Decimal = Field(max_digits=12, decimal_places=3)
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("quantity_kg")
    @classmethod
    def _not_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Adjustment cannot be zero")
        return value


class StockLotOut(ORMModel):
    id: str
    fruit_id: str
    fruit_name: str | None = None
    sku: str | None = None
    quantity_kg: Quantity
    unit_cost: Money
    warehouse: str
    received_at: datetime
    expires_on: date | None
    note: str | None
