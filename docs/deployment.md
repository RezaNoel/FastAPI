# Deployment

## A single machine

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Put a reverse proxy in front. Terminate TLS there. Leave gzip on the proxy if you prefer; Grove already compresses ordinary responses and leaves the live stream alone.

If the proxy sets `X-Forwarded-For` and you trust it, set `TRUST_PROXY=true`. Left false, the rate limiter uses the socket peer, which is the right choice when the peer is the client.

Set:

```
APP_ENV=production
SECRET_KEY=<a long random string>
SEED_ON_STARTUP=false
```

Generate the secret yourself. Do not reuse the Compose example.

## Postgres

```
DATABASE_URL=postgresql+asyncpg://grove:grove@db:5432/grove
AUTO_CREATE_TABLES=false
```

Apply the schema before serving:

```bash
alembic upgrade head
```

`docker compose up --build` does this. The Compose file is a development stack: the database password is `grove`, seeding is on, and the secret is marked as a development secret. Change all three before exposing the port.

## Media

Uploads land in `MEDIA_DIR` (default `media/`). The receipt log is `media/receipts.log`, written by a background task after the order response. Both should live on a volume if the container is replaced.

## Health

`GET /health` does not touch the database. `GET /ready` runs `SELECT 1` and returns 503 when that fails. Point a load balancer at `/ready` and a process supervisor at `/health`.

`GET /ops/metrics` is plain text in the Prometheus exposition format: an info series and a request counter labeled by method, route template, and status.

## Rate limits

Limits are per process, in memory. One Uvicorn worker is the intended shape. Several workers each keep their own window, so the effective ceiling is the configured limit times the worker count. Share a store if that stops being acceptable; `RateLimiter.allow` is the seam.
