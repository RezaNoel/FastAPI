"""Test client against a private in-memory database."""

import os
import tempfile

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="grove-media-")

import pytest
from app.db.base import Base
from app.db.session import engine
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
