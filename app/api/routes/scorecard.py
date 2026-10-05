from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.schemas.scorecard import FullScorecardRead
from app.services.scorecard import get_full_scorecard as get_full_scorecard_service


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


router = APIRouter(prefix="/matches", tags=["scorecard"])


@router.get("/{match_id}/scorecard", response_model=FullScorecardRead)
async def get_full_scorecard(match_id: UUID, session: SessionDependency) -> FullScorecardRead:
    return await get_full_scorecard_service(session, match_id)