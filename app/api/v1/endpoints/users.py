"""House accounts. Role changes are an admin action."""

import math
from typing import Annotated

from fastapi import APIRouter, Query, Security
from sqlalchemy import func, select

from app.api.deps import DbSession, get_principal
from app.models import User
from app.schemas.auth import UserOut, UserUpdate
from app.schemas.common import PROBLEMS, Page
from app.services import audit, identity

router = APIRouter(responses=PROBLEMS)


@router.get("", response_model=Page[UserOut], operation_id="listUsers")
async def list_users(
    session: DbSession,
    actor: Annotated[User, Security(get_principal, scopes=["admin"])],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> Page[UserOut]:
    del actor
    total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    rows = (
        await session.scalars(
            select(User).order_by(User.full_name.asc()).offset((page - 1) * size).limit(size)
        )
    ).all()
    pages = math.ceil(total / size) if total else 0
    return Page(
        items=[identity.user_out(row) for row in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.patch("/{user_id}", response_model=UserOut, operation_id="updateUser")
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: DbSession,
    actor: Annotated[User, Security(get_principal, scopes=["admin"])],
) -> UserOut:
    user = await identity.update_user(session, actor, user_id, payload.model_dump(exclude_unset=True))
    await audit.record(
        session,
        actor_id=actor.id,
        action="user.updated",
        entity="user",
        entity_id=user.id,
        detail={"role": user.role, "is_active": user.is_active},
    )
    return identity.user_out(user)
