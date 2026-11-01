"""The paths a desk actually uses."""

from app.core.limiter import RateLimiter

from tests.helpers import FRUIT, add_user, login


def test_limiter_blocks_after_the_window_fills():
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("desk")[0] is True
    assert limiter.allow("desk")[0] is True
    allowed, remaining = limiter.allow("desk")
    assert allowed is False
    assert remaining == 0


async def test_health_ready_and_metrics(client):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "grove"
    ready = await client.get("/ready")
    assert ready.status_code == 200
    metrics = await client.get("/ops/metrics")
    assert metrics.status_code == 200
    assert "grove_http_requests_total" in metrics.text
    assert "grove_app_info" in metrics.text


async def test_register_login_refresh_and_me(client):
    created = await client.post(
        "/api/v1/auth/register",
        json={"email": "ada@grove.example", "full_name": "Ada Grove", "password": "Harvest2026"},
    )
    assert created.status_code == 201
    assert created.json()["role"] == "clerk"
    assert "password" not in created.json()

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "ada@grove.example", "full_name": "Ada Grove", "password": "Harvest2026"},
    )
    assert duplicate.status_code == 409
    assert duplicate.headers["content-type"].startswith("application/problem+json")

    token = await client.post(
        "/api/v1/auth/token",
        data={"username": "ada@grove.example", "password": "Harvest2026"},
    )
    body = token.json()
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert "orders:write" in me.json()["scopes"]
    assert "admin" not in me.json()["scopes"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert rotated.status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert reused.status_code == 401


async def test_validation_shape(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "full_name": "A", "password": "short"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:grove:problem:validation-failed"
    assert body["errors"]


async def test_catalog_permissions_etag_and_archive(client):
    await add_user("clerk@grove.example", "clerk")
    await add_user("manager@grove.example", "manager")
    clerk = await login(client, "clerk@grove.example")
    manager = await login(client, "manager@grove.example")

    denied = await client.post("/api/v1/fruits", json=FRUIT, headers=clerk)
    assert denied.status_code == 403

    created = await client.post("/api/v1/fruits", json=FRUIT, headers=manager)
    assert created.status_code == 201, created.text
    fruit_id = created.json()["id"]
    assert created.json()["stock_status"] == "out"

    public = await client.get("/api/v1/fruits?category=pome&size=8&sort=name")
    assert public.status_code == 200
    assert public.json()["total"] == 1
    assert public.json()["size"] == 8
    assert "x-request-id" in public.headers

    fetched = await client.get(f"/api/v1/fruits/{fruit_id}")
    etag = fetched.headers["etag"]
    cached = await client.get(f"/api/v1/fruits/{fruit_id}", headers={"If-None-Match": etag})
    assert cached.status_code == 304

    stale = await client.patch(
        f"/api/v1/fruits/{fruit_id}",
        json={"price_per_kg": "4.00"},
        headers={**manager, "If-Match": '"999"'},
    )
    assert stale.status_code == 412
    updated = await client.patch(
        f"/api/v1/fruits/{fruit_id}",
        json={"price_per_kg": "4.00"},
        headers={**manager, "If-Match": etag},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    missing = await client.get("/api/v1/fruits/does-not-exist")
    assert missing.status_code == 404

    archived = await client.delete(f"/api/v1/fruits/{fruit_id}", headers=manager)
    assert archived.status_code == 204
    listed = await client.get("/api/v1/fruits")
    assert listed.json()["total"] == 0


async def test_orders_draw_stock_once_and_restore_on_cancel(client):
    await add_user("manager@grove.example", "manager")
    headers = await login(client, "manager@grove.example")
    fruit = await client.post("/api/v1/fruits", json=FRUIT, headers=headers)
    fruit_id = fruit.json()["id"]
    receipt = await client.post(
        "/api/v1/inventory/receipts",
        json={
            "fruit_id": fruit_id,
            "quantity_kg": "10",
            "unit_cost": "1.25",
            "warehouse": "Cold room A",
        },
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text

    payload = {
        "customer_name": "North Market",
        "lines": [{"fruit_id": fruit_id, "quantity_kg": "4"}],
    }
    key = {**headers, "Idempotency-Key": "ticket-44"}
    first = await client.post("/api/v1/orders", json=payload, headers=key)
    assert first.status_code == 201, first.text
    replay = await client.post("/api/v1/orders", json=payload, headers=key)
    assert replay.status_code == 201
    assert replay.json()["number"] == first.json()["number"]
    assert replay.headers["idempotent-replayed"] == "true"

    on_hand = await client.get(f"/api/v1/fruits/{fruit_id}")
    assert on_hand.json()["quantity_on_hand"] == 6

    conflict = await client.post(
        "/api/v1/orders",
        json={"customer_name": "Other", "lines": [{"fruit_id": fruit_id, "quantity_kg": "1"}]},
        headers=key,
    )
    assert conflict.status_code == 409

    short = await client.post(
        "/api/v1/orders",
        json={"customer_name": "Too Much", "lines": [{"fruit_id": fruit_id, "quantity_kg": "7"}]},
        headers=headers,
    )
    assert short.status_code == 409
    still = await client.get(f"/api/v1/fruits/{fruit_id}")
    assert still.json()["quantity_on_hand"] == 6

    cancelled = await client.post(f"/api/v1/orders/{first.json()['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    restored = await client.get(f"/api/v1/fruits/{fruit_id}")
    assert restored.json()["quantity_on_hand"] == 10

    exported = await client.get("/api/v1/fruits/export", headers=headers)
    assert exported.status_code == 200
    assert "TST-APP" in exported.text


async def test_api_key_is_read_only(client):
    await add_user("admin@grove.example", "admin")
    headers = await login(client, "admin@grove.example")
    created = await client.post("/api/v1/keys", json={"name": "Board"}, headers=headers)
    assert created.status_code == 201
    secret = created.json()["secret"]
    assert secret.startswith("grove_")

    listed = await client.get("/api/v1/orders", headers={"X-API-Key": secret})
    assert listed.status_code == 200
    write = await client.post("/api/v1/fruits", json=FRUIT, headers={"X-API-Key": secret})
    assert write.status_code == 403


async def test_upload_rejects_non_images_and_accepts_png(client):
    await add_user("manager@grove.example", "manager")
    headers = await login(client, "manager@grove.example")
    fruit = await client.post("/api/v1/fruits", json=FRUIT, headers=headers)
    fruit_id = fruit.json()["id"]

    rejected = await client.post(
        "/api/v1/uploads",
        data={"fruit_id": fruit_id},
        files={"file": ("note.svg", b"<svg></svg>", "image/svg+xml")},
        headers=headers,
    )
    assert rejected.status_code == 422

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    accepted = await client.post(
        "/api/v1/uploads",
        data={"fruit_id": fruit_id},
        files={"file": ("apple.png", png, "image/png")},
        headers=headers,
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["image_url"].endswith(".png")


async def test_summary_and_adjustment(client):
    await add_user("manager@grove.example", "manager")
    headers = await login(client, "manager@grove.example")
    fruit = await client.post("/api/v1/fruits", json=FRUIT, headers=headers)
    fruit_id = fruit.json()["id"]
    await client.post(
        "/api/v1/inventory/receipts",
        json={"fruit_id": fruit_id, "quantity_kg": "5", "unit_cost": "1.00", "warehouse": "Floor"},
        headers=headers,
    )
    adjusted = await client.post(
        "/api/v1/inventory/adjustments",
        json={"fruit_id": fruit_id, "quantity_kg": "-2", "reason": "Sampled on the floor"},
        headers=headers,
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["quantity_on_hand"] == 3

    summary = await client.get("/api/v1/reports/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["sku_count"] == 1
    assert summary.json()["low_stock"][0]["sku"] == "TST-APP"
