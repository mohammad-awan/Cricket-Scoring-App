from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, status
from app.api.dependencies import QueryDependency, SessionDependency
from app.schemas.common import PageResponse
from app.schemas.tournaments import TournamentCreate, TournamentRead, TournamentUpdate
from app.services.tournaments import archive_tournament, create_tournament, get_tournament, list_tournaments, update_tournament


router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.post("", response_model=TournamentRead, status_code=status.HTTP_201_CREATED)
async def create_tournament_endpoint(
    payload: TournamentCreate,
    session: SessionDependency,
) -> TournamentRead:
    return await create_tournament(session, payload)


@router.get("", response_model=PageResponse[TournamentRead])
async def list_tournaments_endpoint(
    query: QueryDependency,
    session: SessionDependency,
) -> PageResponse[TournamentRead]:
    return await list_tournaments(session, query)


@router.get("/{tournament_id}", response_model=TournamentRead)
async def get_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await get_tournament(session, tournament_id)


@router.patch("/{tournament_id}", response_model=TournamentRead)
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


@router.post("/{tournament_id}/archive", response_model=TournamentRead)
async def archive_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await archive_tournament(
        session,
        tournament_id,
    )
