from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_master_data_query
from app.db.session import get_db_session
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.master_data import (
    PlayerCreate,
    PlayerRead,
    PlayerUpdate,
    TeamCreate,
    TeamRead,
    TeamUpdate,
    TournamentCreate,
    TournamentRead,
    TournamentUpdate,
    VenueCreate,
    VenueRead,
    VenueUpdate,
)
from app.services.master_data import (
    archive_player,
    archive_team,
    archive_tournament,
    archive_venue,
    create_player,
    create_team,
    create_tournament,
    create_venue,
    get_player,
    get_team,
    get_tournament,
    get_venue,
    list_players,
    list_teams,
    list_tournaments,
    list_venues,
    update_player,
    update_team,
    update_tournament,
    update_venue,
)


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
QueryDependency = Annotated[MasterDataQuery, Depends(get_master_data_query)]


router = APIRouter()
teams_router = APIRouter(prefix="/teams", tags=["teams"])


@teams_router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team_endpoint(payload: TeamCreate, session: SessionDependency) -> TeamRead:
    return await create_team(session, payload)


@teams_router.get("", response_model=PageResponse[TeamRead])
async def list_teams_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[TeamRead]:
    return await list_teams(session, query)


@teams_router.get("/{team_id}", response_model=TeamRead)
async def get_team_endpoint(team_id: UUID, session: SessionDependency) -> TeamRead:
    return await get_team(session, team_id)


@teams_router.patch("/{team_id}", response_model=TeamRead)
async def update_team_endpoint(team_id: UUID, payload: TeamUpdate, session: SessionDependency) -> TeamRead:
    return await update_team(session, team_id, payload)


@teams_router.post("/{team_id}/archive", response_model=TeamRead)
async def archive_team_endpoint(team_id: UUID, session: SessionDependency) -> TeamRead:
    return await archive_team(session, team_id)


players_router = APIRouter(prefix="/players", tags=["players"])

@players_router.post("", response_model=PlayerRead, status_code=status.HTTP_201_CREATED)
async def create_player_endpoint(payload: PlayerCreate, session: SessionDependency) -> PlayerRead:
    return await create_player(session, payload)


@players_router.get("", response_model=PageResponse[PlayerRead])
async def list_players_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[PlayerRead]:
    return await list_players(session, query)


@players_router.get("/{player_id}", response_model=PlayerRead)
async def get_player_endpoint(player_id: UUID, session: SessionDependency) -> PlayerRead:
    return await get_player(session, player_id)


@players_router.patch("/{player_id}", response_model=PlayerRead)
async def update_player_endpoint(player_id: UUID, payload: PlayerUpdate, session: SessionDependency) -> PlayerRead:
    return await update_player(session, player_id, payload)


@players_router.post("/{player_id}/archive", response_model=PlayerRead)
async def archive_player_endpoint(player_id: UUID, session: SessionDependency) -> PlayerRead:
    return await archive_player(session, player_id)


venues_router = APIRouter(prefix="/venues", tags=["venues"])


@venues_router.post("", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
async def create_venue_endpoint(payload: VenueCreate, session: SessionDependency) -> VenueRead:
    return await create_venue(session, payload)


@venues_router.get("", response_model=PageResponse[VenueRead])
async def list_venues_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[VenueRead]:
    return await list_venues(session, query)


@venues_router.get("/{venue_id}", response_model=VenueRead)
async def get_venue_endpoint(venue_id: UUID, session: SessionDependency) -> VenueRead:
    return await get_venue(session, venue_id)


@venues_router.patch("/{venue_id}", response_model=VenueRead)
async def update_venue_endpoint(
    venue_id: UUID,
    payload: VenueUpdate,
    session: SessionDependency,
) -> VenueRead:
    return await update_venue(session, venue_id, payload)


@venues_router.post("/{venue_id}/archive", response_model=VenueRead)
async def archive_venue_endpoint(venue_id: UUID, session: SessionDependency) -> VenueRead:
    return await archive_venue(session, venue_id)


tournaments_router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@tournaments_router.post("", response_model=TournamentRead, status_code=status.HTTP_201_CREATED)
async def create_tournament_endpoint(
    payload: TournamentCreate,
    session: SessionDependency,
) -> TournamentRead:
    return await create_tournament(session, payload)


@tournaments_router.get("", response_model=PageResponse[TournamentRead])
async def list_tournaments_endpoint(
    query: QueryDependency,
    session: SessionDependency,
) -> PageResponse[TournamentRead]:
    return await list_tournaments(session, query)


@tournaments_router.get("/{tournament_id}", response_model=TournamentRead)
async def get_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await get_tournament(session, tournament_id)


@tournaments_router.patch("/{tournament_id}", response_model=TournamentRead)
async def update_tournament_endpoint(
    tournament_id: UUID,
    payload: TournamentUpdate,
    session: SessionDependency,
) -> TournamentRead:
    return await update_tournament(
        session,
        tournament_id,
        payload,
    )


@tournaments_router.post("/{tournament_id}/archive", response_model=TournamentRead)
async def archive_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await archive_tournament(
        session,
        tournament_id,
    )


router.include_router(teams_router)
router.include_router(players_router)
router.include_router(venues_router)
router.include_router(tournaments_router)