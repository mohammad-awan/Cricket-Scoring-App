from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, status
from app.api.dependencies import QueryDependency, SessionDependency
from app.schemas.common import PageResponse
from app.schemas.players import PlayerCreate, PlayerRead, PlayerUpdate
from app.services.players import archive_player, create_player, get_player, list_players, update_player


router = APIRouter(prefix="/players", tags=["players"])


@router.post("", response_model=PlayerRead, status_code=status.HTTP_201_CREATED)
async def create_player_endpoint(payload: PlayerCreate, session: SessionDependency) -> PlayerRead:
    return await create_player(session, payload)


@router.get("", response_model=PageResponse[PlayerRead])
async def list_players_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[PlayerRead]:
    return await list_players(session, query)


@router.get("/{player_id}", response_model=PlayerRead)
async def get_player_endpoint(player_id: UUID, session: SessionDependency) -> PlayerRead:
    return await get_player(session, player_id)


@router.patch("/{player_id}", response_model=PlayerRead)
async def update_player_endpoint(player_id: UUID, payload: PlayerUpdate, session: SessionDependency) -> PlayerRead:
    return await update_player(session, player_id, payload)


@router.post("/{player_id}/archive", response_model=PlayerRead)
async def archive_player_endpoint(player_id: UUID, session: SessionDependency) -> PlayerRead:
    return await archive_player(session, player_id)
