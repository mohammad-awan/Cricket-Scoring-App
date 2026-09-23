from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.models.enums import MatchStatus
from app.schemas.common import PageResponse
from app.schemas.match_setup import (
    MatchCreate,
    MatchListRead,
    MatchSetupRead,
    MatchUpdate,
    OpeningInningsSetup,
    PlayingTeamSetup,
    SquadPlayerRead,
    TossSetup,
)

from app.services.match_setup import (
    create_match,
    get_active_squad,
    get_match_setup,
    list_matches,
    mark_match_ready,
    set_playing_team,
    set_toss,
    setup_opening_innings,
    update_match,
)


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/matches", tags=["match setup"])


@router.post("", response_model=MatchSetupRead, status_code=status.HTTP_201_CREATED)
async def create_match_endpoint(
    payload: MatchCreate,
    session: SessionDependency,
) -> MatchSetupRead:

    return await create_match(
        session,
        payload,
    )


@router.get(
    "",
    response_model=PageResponse[
        MatchListRead
    ],
)
async def list_matches_endpoint(
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    match_status: MatchStatus | None = None,

) -> PageResponse[MatchListRead]:

    normalized_search = (
        search.strip()
        if search
        and search.strip()
        else None
    )

    return await list_matches(
        session,
        page=page,
        page_size=page_size,
        search=normalized_search,
        match_status=match_status,
    )


@router.get("/{match_id}", response_model=MatchSetupRead)
async def get_match_endpoint(match_id: UUID, session: SessionDependency) -> MatchSetupRead:
    return await get_match_setup(session, match_id)


@router.patch("/{match_id}", response_model=MatchSetupRead)
async def update_match_endpoint(
    match_id: UUID,
    payload: MatchUpdate,
    session: SessionDependency,
) -> MatchSetupRead:

    return await update_match(session, match_id, payload)


@router.put("/{match_id}/toss", response_model=MatchSetupRead)
async def set_toss_endpoint(
    match_id: UUID,
    payload: TossSetup,
    session: SessionDependency,
) -> MatchSetupRead:

    return await set_toss(session, match_id, payload)


@router.get("/{match_id}/squads/{team_id}", response_model=list[SquadPlayerRead])
async def get_active_squad_endpoint(
    match_id: UUID,
    team_id: UUID,
    session: SessionDependency,
) -> list[SquadPlayerRead]:

    return await get_active_squad(
        session,
        match_id,
        team_id,
    )


@router.put("/{match_id}/playing-team/{team_id}", response_model=MatchSetupRead)
async def set_playing_team_endpoint(
    match_id: UUID,
    team_id: UUID,
    payload: PlayingTeamSetup,
    session: SessionDependency,
) -> MatchSetupRead:

    return await set_playing_team(session, match_id, team_id, payload)


@router.put("/{match_id}/opening-innings", response_model=MatchSetupRead)
async def setup_opening_innings_endpoint(
    match_id: UUID,
    payload: OpeningInningsSetup,
    session: SessionDependency) -> MatchSetupRead:

    return await setup_opening_innings(session, match_id, payload)


@router.post("/{match_id}/ready", response_model=MatchSetupRead)
async def mark_match_ready_endpoint(match_id: UUID, session: SessionDependency) -> MatchSetupRead:
    return await mark_match_ready(session, match_id)
