"""ASGI middleware.

These are written against the raw ASGI interface on purpose. Starlette's
BaseHTTPMiddleware buffers response bodies and breaks server-sent events.
"""

import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import request_id_var
from app.core.metrics import metrics

EXEMPT_PREFIXES = ("/health", "/ready", "/ops", "/static", "/media", "/docs", "/redoc")
EXEMPT_EXACT = {"/", "/openapi.json", "/favicon.ico"}


def _header(scope: Scope, name: str) -> str | None:
    target = name.lower().encode()
    for key, value in scope.get("headers", []):
        if key == target:
            return value.decode("latin-1")
    return None


def client_key(scope: Scope) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        forwarded = _header(scope, "x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = scope.get("client")
    if client and client[0]:
        return client[0]
    return "-"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Process-Time"] = f"{time.perf_counter() - started:.4f}"
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in EXEMPT_EXACT or path.startswith(EXEMPT_PREFIXES) or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        auth = path.startswith("/api/v1/auth")
        cap = settings.auth_rate_limit_per_minute if auth else settings.rate_limit_per_minute
        bucket = "auth" if auth else "api"
        allowed, remaining = limiter.allow(f"{client_key(scope)}:{bucket}", limit=cap)
        if not allowed:
            response = JSONResponse(
                {
                    "type": "urn:grove:problem:rate-limited",
                    "title": "Too many requests",
                    "status": 429,
                    "detail": "Slow down and retry shortly.",
                    "instance": path,
                    "request_id": scope.get("state", {}).get("request_id", "-"),
                },
                status_code=429,
                media_type="application/problem+json",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(cap),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(cap)
                headers["X-RateLimit-Remaining"] = str(remaining)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_holder: dict[str, int] = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or "unmatched"
            metrics.observe(scope.get("method", "GET"), path, status_holder["status"])


class SelectiveGZip:
    """Gzip ordinary responses and leave the live stream alone."""

    def __init__(self, app: ASGIApp) -> None:
        from starlette.middleware.gzip import GZipMiddleware

        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=800)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path.startswith("/api/v1/live"):
            await self.app(scope, receive, send)
            return
        await self._gzip(scope, receive, send)
