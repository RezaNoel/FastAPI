"""Importing this package registers every table on the metadata."""

from app.models.tables import (
    ApiKey,
    AuditEvent,
    Fruit,
    IdempotencyKey,
    Order,
    OrderLine,
    RefreshToken,
    StockLot,
    Supplier,
    User,
)

__all__ = [
    "ApiKey",
    "AuditEvent",
    "Fruit",
    "IdempotencyKey",
    "Order",
    "OrderLine",
    "RefreshToken",
    "StockLot",
    "Supplier",
    "User",
]
