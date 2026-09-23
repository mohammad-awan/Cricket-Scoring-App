from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.schemas.match_setup import (
    SquadMemberCreate,
    TeamSquadMembershipRead,
)
from app.services.team_squads import (
    add_player_to_team_squad,
    deactivate_team_squad_member,
    list_team_squad,
)


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/teams", tags=["team squads"])


@router.get("/{team_id}/squad", response_model=list[TeamSquadMembershipRead])
async def list_team_squad_endpoint(
    team_id: UUID,
    session: SessionDependency,
) -> list[TeamSquadMembershipRead]:

    return await list_team_squad(session, team_id)


@router.post("/{team_id}/squad", response_model=TeamSquadMembershipRead, status_code=status.HTTP_201_CREATED)
async def add_player_to_team_squad_endpoint(
    team_id: UUID,
    payload: SquadMemberCreate,
    session: SessionDependency,
) -> TeamSquadMembershipRead:

    return await add_player_to_team_squad(session, team_id, payload)


@router.post("/{team_id}/squad/{player_id}/deactivate", response_model=TeamSquadMembershipRead)
async def deactivate_team_squad_member_endpoint(
    team_id: UUID,
    player_id: UUID,
    session: SessionDependency,
) -> TeamSquadMembershipRead:

    return await deactivate_team_squad_member(session, team_id, player_id)