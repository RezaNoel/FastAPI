"""Password hashing, JWT access tokens, and the role-to-scope map."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

ROLES = ("clerk", "manager", "admin")

ROLE_SCOPES: dict[str, set[str]] = {
    "clerk": {
        "catalog:read",
        "inventory:read",
        "orders:read",
        "orders:write",
        "suppliers:read",
        "reports:read",
    },
    "manager": {
        "catalog:read",
        "catalog:write",
        "inventory:read",
        "inventory:write",
        "orders:read",
        "orders:write",
        "orders:fulfill",
        "suppliers:read",
        "suppliers:write",
        "reports:read",
        "audit:read",
    },
    "admin": {
        "catalog:read",
        "catalog:write",
        "inventory:read",
        "inventory:write",
        "orders:read",
        "orders:write",
        "orders:fulfill",
        "suppliers:read",
        "suppliers:write",
        "reports:read",
        "audit:read",
        "admin",
    },
}

# Machine keys never inherit the owner's role. A leaked key can read the floor,
# not rewrite it.
KEY_SCOPES = {
    "catalog:read",
    "inventory:read",
    "orders:read",
    "suppliers:read",
    "reports:read",
}

OAUTH_SCOPES = {
    "catalog:read": "Read the produce catalog",
    "catalog:write": "Change the catalog",
    "inventory:read": "Read stock lots",
    "inventory:write": "Receive and adjust stock",
    "orders:read": "Read orders",
    "orders:write": "Open and cancel orders",
    "orders:fulfill": "Mark orders fulfilled",
    "suppliers:read": "Read growers",
    "suppliers:write": "Change growers",
    "reports:read": "Read the floor summary",
    "audit:read": "Read the audit log",
    "admin": "Manage people and API keys",
}


def scopes_for(role: str) -> set[str]:
    return set(ROLE_SCOPES.get(role, set()))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _encode(payload: dict[str, Any], *, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    body = dict(payload)
    body["iat"] = int(now.timestamp())
    body["exp"] = int((now + expires_delta).timestamp())
    return jwt.encode(body, settings.secret_key, algorithm="HS256")


def create_access_token(*, user_id: str, role: str, scopes: set[str]) -> tuple[str, int]:
    settings = get_settings()
    minutes = settings.access_token_minutes
    token = _encode(
        {
            "sub": user_id,
            "role": role,
            "scopes": sorted(scopes),
            "typ": "access",
        },
        expires_delta=timedelta(minutes=minutes),
    )
    return token, minutes * 60


def create_refresh_token(*, user_id: str, jti: str) -> str:
    settings = get_settings()
    return _encode(
        {"sub": user_id, "jti": jti, "typ": "refresh"},
        expires_delta=timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc


def new_api_key() -> tuple[str, str, str]:
    """Return (full secret, prefix, hash). The secret is shown once."""
    secret = f"grove_{secrets.token_urlsafe(32)}"
    prefix = secret[:12]
    return secret, prefix, sha256(secret)
