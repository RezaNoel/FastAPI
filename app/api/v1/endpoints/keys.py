"""Read-only machine keys. The secret is returned once."""

from typing import Annotated

from fastapi import APIRouter, Security, status
from sqlalchemy import select

from app.api.deps import DbSession, get_principal
from app.core.problems import NotFound
from app.db.base import utcnow
from app.models import ApiKey, User
from app.schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.schemas.common import PROBLEMS
from app.services import audit, identity

router = APIRouter(responses=PROBLEMS)


@router.get("", response_model=list[ApiKeyOut], operation_id="listApiKeys")
async def list_keys(
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["admin"])],
) -> list[ApiKeyOut]:
    rows = (
        await session.scalars(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
        )
    ).all()
    return [identity.key_out(row) for row in rows]


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    operation_id="createApiKey",
)
async def create_key(
    payload: ApiKeyCreate,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["admin"])],
) -> ApiKeyCreated:
    created = await identity.create_api_key(session, user, payload.name)
    await audit.record(
        session,
        actor_id=user.id,
        action="apikey.created",
        entity="api_key",
        entity_id=created.id,
        detail={"name": created.name, "prefix": created.prefix},
    )
    return created


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="revokeApiKey")
async def revoke_key(
    key_id: str,
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["admin"])],
) -> None:
    row = await session.get(ApiKey, key_id)
    if row is None or row.user_id != user.id:
        raise NotFound("API key not found.")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        await audit.record(
            session,
            actor_id=user.id,
            action="apikey.revoked",
            entity="api_key",
            entity_id=row.id,
            detail={"prefix": row.prefix},
        )
