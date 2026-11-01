"""Accounts, sessions, and machine keys."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.problems import Conflict, NotFound, Unauthorized
from app.core.security import (
    KEY_SCOPES,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_api_key,
    scopes_for,
    sha256,
    verify_password,
)
from app.models import ApiKey, RefreshToken, User
from app.schemas.auth import ApiKeyCreated, ApiKeyOut, TokenPair, UserOut


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        scopes=sorted(scopes_for(user.role)),
        created_at=user.created_at,
    )


async def register(session: AsyncSession, *, email: str, full_name: str, password: str) -> User:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        raise Conflict("An account with that email already exists.")
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role="clerk",
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.hashed_password):
        raise Unauthorized("Email or password is wrong.")
    if not user.is_active:
        raise Unauthorized("This account is inactive.")
    return user


async def issue_tokens(session: AsyncSession, user: User, requested: list[str] | None) -> TokenPair:
    role_scopes = scopes_for(user.role)
    if requested:
        granted = role_scopes.intersection(requested)
        if not granted:
            raise Unauthorized("None of the requested scopes are available to this account.")
    else:
        granted = role_scopes

    access, expires_in = create_access_token(user_id=user.id, role=user.role, scopes=granted)
    jti = str(uuid.uuid4())
    refresh = create_refresh_token(user_id=user.id, jti=jti)
    settings = get_settings()
    session.add(
        RefreshToken(
            id=jti,
            user_id=user.id,
            token_hash=sha256(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    await session.flush()
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in)


async def rotate_refresh(session: AsyncSession, raw_token: str) -> TokenPair:
    try:
        payload = decode_token(raw_token)
    except ValueError as exc:
        raise Unauthorized("Refresh token is invalid.") from exc
    if payload.get("typ") != "refresh":
        raise Unauthorized("Refresh token is invalid.")

    stored = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_token)))
    if stored is None or stored.revoked_at is not None:
        raise Unauthorized("Refresh token is no longer valid.")
    if stored.expires_at < datetime.now(UTC):
        raise Unauthorized("Refresh token has expired.")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("This account is inactive.")

    stored.revoked_at = datetime.now(UTC)
    return await issue_tokens(session, user, None)


async def revoke_refresh(session: AsyncSession, raw_token: str) -> None:
    stored = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_token)))
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise Unauthorized("Current password is wrong.")
    user.hashed_password = hash_password(new_password)
    user.updated_at = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now


def principal_scopes(user: User, token_scopes: list[str]) -> set[str]:
    """Role is the source of truth; the token can only narrow it."""
    return scopes_for(user.role).intersection(token_scopes)


async def resolve_api_key(session: AsyncSession, secret: str) -> tuple[User, set[str]]:
    row = await session.scalar(select(ApiKey).where(ApiKey.key_hash == sha256(secret)))
    if row is None or row.revoked_at is not None:
        raise Unauthorized("API key is invalid.")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("API key is invalid.")
    row.last_used_at = datetime.now(UTC)
    return user, set(KEY_SCOPES)


async def create_api_key(session: AsyncSession, user: User, name: str) -> ApiKeyCreated:
    secret, prefix, digest = new_api_key()
    row = ApiKey(user_id=user.id, name=name.strip(), prefix=prefix, key_hash=digest)
    session.add(row)
    await session.flush()
    return ApiKeyCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=None,
        revoked_at=None,
        secret=secret,
    )


def key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut.model_validate(row)


async def update_user(session: AsyncSession, actor: User, user_id: str, changes: dict) -> User:
    if not changes:
        raise Conflict("Provide a role or an active flag.")
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    if user.id == actor.id and changes.get("is_active") is False:
        raise Conflict("You cannot deactivate yourself.")
    if user.id == actor.id and "role" in changes and changes["role"] != actor.role:
        raise Conflict("You cannot change your own role.")
    if "role" in changes and changes["role"] is not None:
        user.role = changes["role"]
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
    user.updated_at = datetime.now(UTC)
    await session.flush()
    return user
