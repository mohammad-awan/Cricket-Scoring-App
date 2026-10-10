from __future__ import annotations
from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.schemas.scorecard import FullScorecardRead
from app.schemas.scoring import ScoringStateRead


class LiveEventType(str, Enum):
    SNAPSHOT = "snapshot"
    DELIVERY_RECORDED = "delivery_recorded"
    DELIVERY_CORRECTED = "delivery_corrected"
    BOWLER_CHANGED = "bowler_changed"
    INNINGS_ENDED = "innings_ended"
    INNINGS_STARTED = "innings_started"
    BATTING_ORDER_CHANGED = "batting_order_changed"
    RETIREMENT_RECORDED = "retirement_recorded"
    RETIREMENT_CORRECTED = "retirement_corrected"


class LiveMatchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: LiveEventType
    match_id: UUID
    sent_at: datetime
    scoring: ScoringStateRead
    scorecard: FullScorecardRead

