"""Grove application factory.

Run it with `uvicorn app.main:app --reload`.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metrics import metrics
from app.core.middleware import (
    MetricsMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SelectiveGZip,
)
from app.core.problems import AppError, problem_response
from app.db.base import Base
from app.db.seed import seed_if_empty
from app.db.session import engine
from app.models import tables as _tables  # noqa: F401

logger = logging.getLogger("grove")
STATIC_DIR = Path(__file__).resolve().parent / "static"

DESCRIPTION = """
Grove is the operations API for a produce house: catalog, stock, orders, and a live wire of what just moved.

**Authentication.** Use the Authorize button. The password grant is `POST /api/v1/auth/token`
and `username` is the email. Scopes are limited by role. A machine client can send `X-API-Key`
instead of a bearer token; keys are read-only and do not inherit the owner's role.

**Concurrency.** `GET /fruits/{id}` returns an `ETag`. Send it back as `If-Match` when you patch that row.

**Retries.** `POST /orders` accepts `Idempotency-Key`. The same key and body replay the original order
and do not draw stock twice.

Demo accounts are in the project README. This service replaces the original in-memory fruit list.
"""

TAGS = [
    {
        "name": "Authentication",
        "description": "Accounts, the OAuth2 password grant, and refresh rotation.",
    },
    {"name": "Users", "description": "House roles. Admin only."},
    {"name": "Catalog", "description": "The produce book. Reads are public."},
    {"name": "Suppliers", "description": "Growers behind the catalog."},
    {"name": "Inventory", "description": "Lots, receipts, and FIFO adjustments."},
    {"name": "Orders", "description": "Sales. Confirming an order draws stock."},
    {"name": "Uploads", "description": "Catalog photographs."},
    {"name": "Reports", "description": "The opening-screen summary."},
    {"name": "API keys", "description": "Read-only machine credentials."},
    {"name": "Audit", "description": "Who changed the books."},
    {"name": "Live", "description": "Websocket and server-sent activity."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.assert_runtime_safety()
    if settings.app_env != "production" and settings.secret_key.startswith("dev-"):
        logger.warning("SECRET_KEY is the development default. Do not use it in production.")
    settings.media_path.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables and settings.app_env != "test":
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.app_env != "test":
        await seed_if_empty()
    yield


def _validation_errors(exc: RequestValidationError) -> list[dict]:
    cleaned = []
    for error in exc.errors():
        item = {key: value for key, value in error.items() if key != "ctx"}
        if "ctx" in error and isinstance(error["ctx"], dict):
            item["ctx"] = {key: str(value) for key, value in error["ctx"].items()}
        cleaned.append(item)
    return cleaned


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Grove API",
        version=__version__,
        summary="Produce operations for a single house.",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_tags=TAGS,
        contact={"name": "RezaNoel", "url": "https://github.com/RezaNoel/FastAPI"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )

    app.add_middleware(SelectiveGZip)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Process-Time",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "ETag",
            "Idempotent-Replayed",
        ],
    )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return problem_response(
            status=exc.status,
            title=exc.title,
            detail=exc.detail,
            request=request,
            type_name=exc.type_name,
            extra=exc.extra,
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        titles = {
            400: "Bad request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not found",
            409: "Conflict",
            422: "Unprocessable",
        }
        return problem_response(
            status=exc.status_code,
            title=titles.get(exc.status_code, "Request failed"),
            detail=detail,
            request=request,
            type_name=titles.get(exc.status_code, "error").lower().replace(" ", "-"),
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            status=422,
            title="Validation failed",
            detail="The request body or parameters are not valid.",
            request=request,
            type_name="validation-failed",
            errors=_validation_errors(exc),
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        detail = str(exc) if settings.debug else "Something in the house failed."
        return problem_response(
            status=500,
            title="Server error",
            detail=detail,
            request=request,
            type_name="server-error",
        )

    app.include_router(api_router, prefix="/api/v1")

    ops = FastAPI(title="Grove Ops", docs_url=None, redoc_url=None, openapi_url=None)

    @ops.get("/health")
    async def ops_health() -> dict:
        return {"status": "ok"}

    @ops.get("/metrics")
    async def ops_metrics() -> PlainTextResponse:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    app.mount("/ops", ops)

    @app.get("/health", tags=["Ops"], operation_id="health")
    async def health() -> dict:
        return {"status": "ok", "service": "grove", "version": __version__}

    @app.get("/ready", tags=["Ops"], operation_id="ready")
    async def ready(session: DbSession) -> dict:
        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.exception("readiness check failed")
            raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
        return {"status": "ready"}

    @app.get("/docs", include_in_schema=False)
    async def swagger():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Grove API",
            swagger_favicon_url="/static/favicon.svg",
            swagger_ui_parameters={"displayRequestDuration": True, "tryItOutEnabled": True},
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc():
        return get_redoc_html(
            openapi_url="/openapi.json",
            title="Grove API",
            redoc_favicon_url="/static/favicon.svg",
        )

    settings.media_path.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.media_path), name="media")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def floor_ui() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
