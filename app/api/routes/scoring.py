from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.schemas.scoring import BowlerChange, DeliveryCreate, NextInningsCreate, ScoringStateRead
from app.services.scoring import (
    change_bowler,
    end_innings,
    get_scoring_state,
    record_delivery,
    start_next_innings,
)

SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]

router = APIRouter(prefix="/matches", tags=["scoring"])

@router.get("/{match_id}/scoring", response_model=(ScoringStateRead))
async def get_scoring_state_endpoint(match_id: UUID, session: SessionDependency) -> ScoringStateRead:
    return await get_scoring_state(session, match_id)



@router.post("/{match_id}/scoring/deliveries", response_model=(ScoringStateRead), status_code=(status.HTTP_201_CREATED))
async def record_delivery_endpoint(
    match_id: UUID,
    payload: DeliveryCreate,
    session: SessionDependency,
) -> ScoringStateRead:

    return await record_delivery(session, match_id, payload)


@router.put("/{match_id}/scoring/bowler", response_model=ScoringStateRead)
async def change_bowler_endpoint(match_id: UUID, payload: BowlerChange, session: SessionDependency) -> ScoringStateRead:
    return await change_bowler(session, match_id, payload)


@router.post("/{match_id}/scoring/innings/end", response_model=ScoringStateRead)
async def end_innings_endpoint(match_id: UUID, session: SessionDependency) -> ScoringStateRead:
    return await end_innings(session, match_id)


@router.post("/{match_id}/scoring/innings", response_model=ScoringStateRead, status_code=status.HTTP_201_CREATED)
async def start_next_innings_endpoint(
    match_id: UUID,
    payload: NextInningsCreate,
    session: SessionDependency,
) -> ScoringStateRead:
    return await start_next_innings(session, match_id, payload)
