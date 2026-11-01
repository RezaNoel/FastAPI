"""Catalog photographs. SVG is refused; the file is checked by signature, not just the header."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, File, Form, Security, UploadFile

from app.api.deps import DbSession, get_principal
from app.core.config import get_settings
from app.core.problems import NotFound, Unprocessable
from app.db.base import utcnow
from app.models import Fruit, User
from app.schemas.catalog import FruitOut
from app.schemas.common import PROBLEMS
from app.services import audit, catalog

router = APIRouter(responses=PROBLEMS)

MAX_BYTES = 2 * 1024 * 1024


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    return None


@router.post("", response_model=FruitOut, status_code=201, operation_id="uploadFruitImage")
async def upload_fruit_image(
    session: DbSession,
    user: Annotated[User, Security(get_principal, scopes=["catalog:write"])],
    fruit_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> FruitOut:
    fruit = await session.get(Fruit, fruit_id)
    if fruit is None or fruit.archived_at is not None:
        raise NotFound("Fruit not found.")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise Unprocessable("Images must be 2 MB or smaller.")
    extension = _sniff(data)
    if extension is None:
        raise Unprocessable("Upload a JPEG, PNG, or WebP image.")

    relative = f"catalog/{uuid.uuid4().hex}{extension}"
    settings = get_settings()
    destination = settings.media_path / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    fruit.image_path = relative
    fruit.version += 1
    fruit.updated_at = utcnow()
    await session.flush()
    await audit.record(
        session,
        actor_id=user.id,
        action="fruit.image",
        entity="fruit",
        entity_id=fruit.id,
        detail={"path": relative},
    )
    return await catalog.get_fruit(session, fruit.id, Decimal(str(settings.low_stock_kg)))
