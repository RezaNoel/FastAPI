"""The numbers on the opening screen."""

from typing import Annotated

from fastapi import APIRouter, Security

from app.api.deps import DbSession, get_principal
from app.models import User
from app.schemas.commerce import SummaryOut
from app.schemas.common import PROBLEMS
from app.services import reports

router = APIRouter(responses=PROBLEMS)


@router.get("/summary", response_model=SummaryOut, operation_id="floorSummary")
async def floor_summary(
    session: DbSession,
    _: Annotated[User, Security(get_principal, scopes=["reports:read"])],
) -> SummaryOut:
    return await reports.summary(session)
