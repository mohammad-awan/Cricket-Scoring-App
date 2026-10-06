from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID
from fastapi import WebSocket
from app.db.session import AsyncSessionFactory
from app.schemas.realtime import LiveEventType, LiveMatchEvent
from app.services.scorecard import get_full_scorecard
from app.services.scoring import get_scoring_state


logger = logging.getLogger(__name__)


class MatchConnectionManager:
    """
    Keeps active WebSocket
    connections separated by match.

    One match can have:

    - scorer
    - live viewers
    - scorecard viewers

    all connected simultaneously.
    """

    def __init__(self) -> None:
        self.connection: dict[UUID, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()


    async def connect(self, match_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connection[match_id].add(websocket)


    async def disconnect(self, match_id: UUID, websocket: WebSocket) -> None:
        async with self.lock:
            connections = self.connection.get(match_id)

            if connections is not None:
                connections.discard(websocket)

                if not connections:
                    self.connection.pop(match_id, None)


    async def broadcast(self, match_id: UUID, payload: dict) -> None:
        async with self.lock:
            connections = list(self.connection.get(match_id, set()))

        disconnected: list[WebSocket] = []

        for websocket in connections:
            try:
                await websocket.send_json(payload)

            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            await self.disconnect(match_id, websocket)

    async def connection_count(self, match_id: UUID) -> int:
        async with self.lock:
            return len(self.connection.get(match_id, set()))



live_connections = MatchConnectionManager()

async def build_live_event(match_id: UUID, event_type: LiveEventType) -> LiveMatchEvent:
    """
    Build authoritative live state.

    IMPORTANT:

    A completely new short-lived
    AsyncSession is created here.

    The WebSocket connection does
    NOT hold a database session open.
    """

    async with AsyncSessionFactory() as session:
        scoring = await get_scoring_state(session, match_id)
        scorecard = await get_full_scorecard(session, match_id)

        return LiveMatchEvent(
            event_type=event_type,
            match_id=match_id,
            sent_at=datetime.now(timezone.utc),
            scoring=scoring,
            scorecard=scorecard
    
        )

async def publish_committed_match_state(match_id: UUID, event_type: LiveEventType) -> None:
    """
    Broadcast ONLY database-confirmed
    state.

    This function must only be called
    after the normal scoring service
    has completed successfully.

    If the transaction rolls back,
    execution never reaches here.
    """

    try:
        event = (
            await build_live_event(match_id, event_type))


        await live_connections.broadcast(match_id, event.model_dump(mode="json"))


    except Exception:
        # WebSocket failure must never
        # make a successful scoring
        # transaction look failed to
        # the scorer.
        #
        # A committed delivery should
        # never be submitted twice just
        # because a viewer connection
        # had a problem.

        logger.exception(
            (
                "Committed match state "
                "could not be broadcast "
                "for match %s"
            ),
            match_id,
        )



