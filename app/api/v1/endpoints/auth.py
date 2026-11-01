"""Registration, the OAuth2 password flow, and session rotation."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DbSession, get_principal
from app.models import User
from app.schemas.auth import PasswordChange, RefreshIn, RegisterIn, TokenPair, UserOut
from app.schemas.common import PROBLEMS
from app.services import audit, identity

router = APIRouter(responses=PROBLEMS)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="register",
)
async def register(payload: RegisterIn, session: DbSession) -> UserOut:
    """Open a clerk account. An admin promotes people from the house desk."""
    user = await identity.register(
        session,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    await audit.record(
        session,
        actor_id=user.id,
        action="user.registered",
        entity="user",
        entity_id=user.id,
        detail={"email": user.email},
    )
    return identity.user_out(user)


@router.post("/token", response_model=TokenPair, operation_id="issueToken")
async def issue_token(
    session: DbSession,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPair:
    """OAuth2 password grant. `username` is the email address."""
    user = await identity.authenticate(session, form.username, form.password)
    return await identity.issue_tokens(session, user, form.scopes)


@router.post("/refresh", response_model=TokenPair, operation_id="refreshToken")
async def refresh(payload: RefreshIn, session: DbSession) -> TokenPair:
    """Rotate a refresh token. The presented token is revoked."""
    return await identity.rotate_refresh(session, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout(payload: RefreshIn, session: DbSession) -> None:
    await identity.revoke_refresh(session, payload.refresh_token)


@router.get("/me", response_model=UserOut, operation_id="currentUser")
async def me(user: Annotated[User, Security(get_principal)]) -> UserOut:
    return identity.user_out(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, operation_id="changePassword")
async def change_password(
    payload: PasswordChange,
    session: DbSession,
    user: Annotated[User, Security(get_principal)],
) -> None:
    """Change password and revoke every refresh token for this account."""
    await identity.change_password(
        session,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
