# Architecture

Grove is one FastAPI process. The floor UI is static files on the same origin. Persistence is SQLAlchemy 2 async, SQLite by default and Postgres when `DATABASE_URL` says so.

```
app/
  main.py            application factory, docs, health, static floor
  api/               HTTP: dependencies, routers, status codes
  services/          rules: stock, orders, tokens, the live hub
  models/            tables
  schemas/           request and response contracts
  core/              settings, passwords, tokens, errors, middleware
  db/                engine, session, seed
  static/            the floor
alembic/             schema migrations for the Postgres path
tests/
```

Routes do not contain business rules. They validate, call a service, and record an audit line. Services raise `AppError`. The application turns that into a problem document.

## Request path

Outermost middleware first:

1. CORS.
2. Request context. A request id goes on the response and into the log line.
3. Metrics. The route template is the label, not the raw path, so ids do not explode the series.
4. Rate limit. `/api` only. Auth routes have a tighter bucket. Static files, docs, and health are exempt.
5. Gzip, except `/api/v1/live`, which is a stream and must not be buffered.

The database session is a dependency with `yield`. It commits if the request succeeds and rolls back if it does not. The same session is reused when several dependencies ask for it in one request.

## Stock

A lot is a received weight in a named room. Selling and negative adjustments consume the oldest remaining lot. When a lot hits zero it is deleted. Cancelling a confirmed order writes the weight back as a new lot in Returns. The order line stores the fruit name, SKU, and unit price from the moment of sale.

## Live wire

`EventHub` is in-process. Publishing fans out to open websockets and to server-sent-event subscribers, and keeps a short history for the wire page. One process is the assumption. A second instance would need a shared bus; the hub is the seam for that.

## Two ways to create the schema

Local `uvicorn` runs `create_all` and then seeds an empty database. That is the path with the least setup.

Compose sets `AUTO_CREATE_TABLES=false` and runs `alembic upgrade head` before the server. Do not point both mechanisms at the same populated database: Alembic will refuse to create tables that `create_all` already built, because it has no revision row.

## Ops, mounted separately

`/health` and `/ready` live on the public app. `/ops` is a mounted sub-application with no OpenAPI of its own: liveness and the metrics scrape. A scraper does not need the public schema.
