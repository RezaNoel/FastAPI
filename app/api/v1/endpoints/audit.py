"""Who changed the books."""

import math
from typing import Annotated

from fastapi import APIRouter, Query, Security
from sqlalchemy import func, select

from app.api.deps import DbSession, get_principal
from app.models import AuditEvent, User
from app.schemas.commerce import AuditOut
from app.schemas.common import PROBLEMS, Page

router = APIRouter(responses=PROBLEMS)


@router.get("", response_model=Page[AuditOut], operation_id="listAudit")
async def list_audit(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["audit:read"])],
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
) -> Page[AuditOut]:
    total = int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    rows = (
        await session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).offset((page - 1) * size).limit(size)
        )
    ).all()
    names: dict[str, str] = {}
    actor_ids = {row.actor_id for row in rows if row.actor_id}
    if actor_ids:
        people = (await session.scalars(select(User).where(User.id.in_(actor_ids)))).all()
        names = {person.id: person.full_name for person in people}
    items = [
        AuditOut(
            id=row.id,
            actor_id=row.actor_id,
            actor_name=names.get(row.actor_id or ""),
            action=row.action,
            entity=row.entity,
            entity_id=row.entity_id,
            detail=row.detail,
            created_at=row.created_at,
        )
        for row in rows
    ]
    pages = math.ceil(total / size) if total else 0
    return Page(items=items, total=total, page=page, size=size, pages=pages)
