from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, status
from app.api.dependencies import QueryDependency, SessionDependency
from app.schemas.common import PageResponse
from app.schemas.teams import TeamCreate, TeamRead, TeamUpdate
from app.services.teams import archive_team, create_team, get_team, list_teams, update_team


router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team_endpoint(payload: TeamCreate, session: SessionDependency) -> TeamRead:
    return await create_team(session, payload)


@router.get("", response_model=PageResponse[TeamRead])
async def list_teams_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[TeamRead]:
    return await list_teams(session, query)


@router.get("/{team_id}", response_model=TeamRead)
async def get_team_endpoint(team_id: UUID, session: SessionDependency) -> TeamRead:
    return await get_team(session, team_id)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team_endpoint(team_id: UUID, payload: TeamUpdate, session: SessionDependency) -> TeamRead:
    return await update_team(session, team_id, payload)


@router.post("/{team_id}/archive", response_model=TeamRead)
async def archive_team_endpoint(team_id: UUID, session: SessionDependency) -> TeamRead:
    return await archive_team(session, team_id)
