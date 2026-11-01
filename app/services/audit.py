"""Append-only record of who changed what."""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def record(
    session: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    entity: str,
    entity_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=json.dumps(detail, default=str) if detail else None,
        )
    )
