"""Shared makers for the API tests."""

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from httpx import AsyncClient

FRUIT = {
    "sku": "TST-APP",
    "name": "Test Apple",
    "category": "pome",
    "origin": "Test Valley",
    "description": "Crisp enough for the cold room.",
    "price_per_kg": "3.50",
    "is_seasonal": True,
    "season_label": "Autumn",
}


async def add_user(email: str, role: str, password: str = "Harvest2026") -> User:
    async with SessionLocal() as session:
        user = User(
            email=email,
            full_name=role.title(),
            hashed_password=hash_password(password),
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def login(client: AsyncClient, email: str, password: str = "Harvest2026") -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
