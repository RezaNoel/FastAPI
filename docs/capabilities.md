# Framework surface

Grove is a produce-house service first. This page is the index of where the framework shows up, for anyone reading the code rather than the floor.

| Surface | Where |
| --- | --- |
| Application factory and lifespan | `app/main.py` |
| Versioned `APIRouter`, tags, `operation_id` | `app/api/v1/router.py` and each endpoint module |
| Pydantic v2 models, validators, serializers | `app/schemas/` |
| Query parameter model | `FruitFilters` on `GET /fruits` |
| `response_model`, status codes, `Header`, `Response` | catalog and orders |
| Dependency injection with `yield` | `get_session` |
| `Security`, OAuth2 password flow, scopes | `app/api/deps.py`, `POST /auth/token` |
| `APIKeyHeader` | `X-API-Key` |
| `Form`, `File`, `UploadFile` | `POST /uploads` |
| `BackgroundTasks` | receipt log after an order |
| `WebSocket` | `/api/v1/live/ws` |
| `StreamingResponse` CSV | `GET /fruits/export` |
| Server-sent events | `GET /api/v1/live/events` |
| CORS, gzip, custom ASGI middleware | `app/core/middleware.py` |
| Exception handlers, validation errors | `create_app` |
| Custom Swagger and ReDoc | `/docs`, `/redoc` |
| `StaticFiles` and `FileResponse` | `/static`, `/media`, `/` |
| Mounted sub-application | `/ops` |
| Settings from the environment | `app/core/config.py` |
| Async SQLAlchemy session | `app/db/session.py` |
| Alembic | `alembic/` |
| OpenAPI problem responses | `Problem` on the routers |
| ETag and `If-Match` | fruit get and patch |
| Idempotency-Key | `POST /orders` |

Middleware is raw ASGI. `BaseHTTPMiddleware` buffers bodies and breaks the event stream, so it is not used.

Errors share one shape, `application/problem+json`:

```json
{
  "type": "urn:grove:problem:not-found",
  "title": "Not found",
  "status": 404,
  "detail": "Fruit not found.",
  "instance": "/api/v1/fruits/...",
  "request_id": "..."
}
```

Validation errors add an `errors` array. 401 responses include `WWW-Authenticate`.

Catalog reads send `Cache-Control: public, max-age=5` and, for a single fruit, an `ETag` of the row version. `If-None-Match` returns 304. `If-Match` on a patch returns 412 when the version moved.

`POST /orders` stores the idempotency key, the hash of the body, and the response. The same key and body replay that response and set `Idempotent-Replayed: true`. The same key and a different body is a conflict.
