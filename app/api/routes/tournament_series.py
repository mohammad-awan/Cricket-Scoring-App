from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, status
from app.api.dependencies import OrganizerDependency, QueryDependency, SessionDependency
from app.schemas.common import PageResponse
from app.schemas.tournaments import (
    TournamentEditionRead,
    TournamentSeriesCreate,
    TournamentSeriesRead,
    TournamentSeriesUpdate,
)
from app.services import tournament_series as series_services


router = APIRouter(prefix="/tournament-series", tags=["tournament series"])


@router.get("", response_model=PageResponse[TournamentSeriesRead])
async def list_tournament_series_endpoint(
    query: QueryDependency,
    session: SessionDependency,
) -> PageResponse[TournamentSeriesRead]:
    return await series_services.list_tournament_series(session, query)


@router.post("", response_model=TournamentSeriesRead, status_code=status.HTTP_201_CREATED)
async def create_tournament_series_endpoint(
    payload: TournamentSeriesCreate,
    session: SessionDependency,
    _: OrganizerDependency,
) -> TournamentSeriesRead:
    return await series_services.create_tournament_series(session, payload)


@router.get("/{series_id}", response_model=TournamentSeriesRead)
async def get_tournament_series_endpoint(
    series_id: UUID,
    session: SessionDependency,
) -> TournamentSeriesRead:
    return await series_services.get_tournament_series(session, series_id)


@router.patch("/{series_id}", response_model=TournamentSeriesRead)
async def update_tournament_series_endpoint(
    series_id: UUID,
    payload: TournamentSeriesUpdate,
    session: SessionDependency,
    _: OrganizerDependency,
) -> TournamentSeriesRead:
    return await series_services.update_tournament_series(session, series_id, payload)


@router.get("/{series_id}/editions", response_model=list[TournamentEditionRead])
async def list_series_editions_endpoint(
    series_id: UUID,
    session: SessionDependency,
) -> list[TournamentEditionRead]:
    return await series_services.list_series_editions(session, series_id)
