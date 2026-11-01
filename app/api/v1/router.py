"""Versioned API surface."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    fruits,
    inventory,
    keys,
    live,
    orders,
    reports,
    suppliers,
    uploads,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(fruits.router, prefix="/fruits", tags=["Catalog"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["Uploads"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(keys.router, prefix="/keys", tags=["API keys"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit"])
api_router.include_router(live.router, prefix="/live", tags=["Live"])
