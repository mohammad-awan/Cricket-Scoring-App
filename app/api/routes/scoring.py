from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.schemas.batting_order import LiveBattingOrderRead, LiveBattingOrderUpdate
from app.schemas.realtime import LiveEventType
from app.schemas.retirements import RetirementCreate, RetirementUndo
from app.schemas.scoring import (
    BowlerChange,
    DeliveryCreate,
    DeliveryUndo,
    NextInningsCreate,
    ScoringStateRead,
)
from app.services.realtime import publish_committed_match_state
from app.services.scoring import (
    change_bowler,
    create_retirement,
    end_innings,
    get_live_batting_order,
    get_scoring_state,
    rearrange_batting_order,
    record_delivery,
    start_next_innings,
    undo_delivery,
    undo_retirement,
)


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


router = APIRouter(prefix="/matches", tags=["scoring"])


@router.get(
    "/{match_id}/scoring",
    response_model=ScoringStateRead
)
async def get_scoring_state_endpoint(
    match_id: UUID,
    session: SessionDependency,
) -> ScoringStateRead:

    return await get_scoring_state(session, match_id)


@router.post(
    "/{match_id}/scoring/deliveries",
    response_model=ScoringStateRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_delivery_endpoint(
    match_id: UUID,
    payload: DeliveryCreate,
    session: SessionDependency,
) -> ScoringStateRead:
    # Existing service completes
    # transaction first.
    scoring = await record_delivery(session, match_id, payload)
    # Only reached after the service
    # transaction succeeded.

    await publish_committed_match_state(match_id, LiveEventType.DELIVERY_RECORDED)
    return scoring


@router.post(
    (
        "/{match_id}/scoring/"
        "deliveries/{delivery_id}/undo"
    ),
    response_model=ScoringStateRead,
)
async def undo_delivery_endpoint(
    match_id: UUID,
    delivery_id: UUID,
    payload: DeliveryUndo,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = (
        await undo_delivery(
            session,
            match_id,
            delivery_id,
            payload,
        )
    )

    await publish_committed_match_state(match_id, LiveEventType.DELIVERY_CORRECTED)

    return scoring


@router.put(
    "/{match_id}/scoring/bowler",
    response_model=ScoringStateRead,
)
async def change_bowler_endpoint(
    match_id: UUID,
    payload: BowlerChange,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = await change_bowler(session, match_id, payload)
    await publish_committed_match_state(match_id, LiveEventType.BOWLER_CHANGED)
    return scoring


@router.post(
    (
        "/{match_id}/scoring/"
        "innings/end"
    ),
    response_model=ScoringStateRead,
)
async def end_innings_endpoint(
    match_id: UUID,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = await end_innings(session, match_id)
    await publish_committed_match_state(match_id, LiveEventType.INNINGS_ENDED)

    return scoring


@router.post(
    "/{match_id}/scoring/innings",
    response_model=ScoringStateRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_next_innings_endpoint(
    match_id: UUID,
    payload: NextInningsCreate,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = await start_next_innings(session, match_id, payload)
    await publish_committed_match_state(match_id, LiveEventType.INNINGS_STARTED)
    return scoring


@router.get(
    "/{match_id}/scoring/batting-order",
    response_model=LiveBattingOrderRead,
)
async def get_batting_order_endpoint(
    match_id: UUID,
    session: SessionDependency,
) -> LiveBattingOrderRead:

    return await get_live_batting_order(session, match_id)


@router.patch(
    "/{match_id}/scoring/batting-order",
    response_model=LiveBattingOrderRead,
)
async def rearrange_batting_order_endpoint(
    match_id: UUID,
    payload: LiveBattingOrderUpdate,
    session: SessionDependency,
) -> LiveBattingOrderRead:

    lineup = await rearrange_batting_order(session, match_id, payload)
    # The live snapshot carries scoring and scorecard data;
    # clients refresh the lineup from the GET endpoint.
    await publish_committed_match_state(match_id, LiveEventType.BATTING_ORDER_CHANGED)
    return lineup


@router.post(
    "/{match_id}/scoring/retirements",
    response_model=ScoringStateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_retirement_endpoint(
    match_id: UUID,
    payload: RetirementCreate,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = await create_retirement(session, match_id, payload)
    await publish_committed_match_state(match_id, LiveEventType.RETIREMENT_RECORDED)
    return scoring


@router.post(
    "/{match_id}/scoring/retirements/{retirement_id}/undo",
    response_model=ScoringStateRead,
)
async def undo_retirement_endpoint(
    match_id: UUID,
    retirement_id: UUID,
    payload: RetirementUndo,
    session: SessionDependency,
) -> ScoringStateRead:

    scoring = await undo_retirement(session, match_id, retirement_id, payload)
    await publish_committed_match_state(match_id, LiveEventType.RETIREMENT_CORRECTED)
    return scoring
