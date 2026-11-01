"""Request dependencies: database session and the current principal."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Unauthorized
from app.core.security import OAUTH_SCOPES, decode_token
from app.db.session import get_session
from app.models import User
from app.services.identity import principal_scopes, resolve_api_key

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
    scopes=OAUTH_SCOPES,
)
api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="APIKey",
    description="Read-only key. It does not inherit the owner's role.",
)

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_principal(
    security_scopes: SecurityScopes,
    session: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    api_key: Annotated[str | None, Depends(api_key_scheme)] = None,
) -> User:
    user: User | None = None
    held: set[str] = set()

    if token:
        try:
            payload = decode_token(token)
        except ValueError as exc:
            raise Unauthorized("Access token is invalid.") from exc
        if payload.get("typ") != "access":
            raise Unauthorized("Access token is invalid.")
        user = await session.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            raise Unauthorized("This account is inactive.")
        token_scopes = payload.get("scopes") or []
        if not isinstance(token_scopes, list):
            token_scopes = []
        held = principal_scopes(user, [str(scope) for scope in token_scopes])
    elif api_key:
        user, held = await resolve_api_key(session, api_key)
    else:
        raise HTTPException(
            status_code=401,
            detail="Missing credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    missing = [scope for scope in security_scopes.scopes if scope not in held]
    if missing:
        scope_str = security_scopes.scope_str
        raise HTTPException(
            status_code=403,
            detail="This action is outside your scope.",
            headers={"WWW-Authenticate": f'Bearer scope="{scope_str}"'},
        )
    return user
