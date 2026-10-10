from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import  AsyncSession
from app.db.session import get_db_session
from app.schemas.player_profile import PlayerMatchHistoryPageRead, PlayerProfileRead
from app.services.player_profile import get_player_match_history, get_player_profile


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/players", tags=["player-profile"])


@router.get("/{player_id}/profile", response_model=PlayerProfileRead)
async def player_profile_endpoint(
    player_id: UUID,
    session: SessionDependency,
) -> PlayerProfileRead:

    return await get_player_profile(session, player_id)


@router.get("/{player_id}/match-history", response_model=PlayerMatchHistoryPageRead)
async def player_match_history_endpoint(
    player_id: UUID,
    session: SessionDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=10,
        ge=1,
        le=100,
    ),

) -> PlayerMatchHistoryPageRead:

    return await get_player_match_history(
        session,
        player_id,
        page=page,
        page_size=page_size)