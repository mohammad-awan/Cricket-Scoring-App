from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models.enums import InningsStatus, MatchStatus
from app.schemas.match_setup import OpeningInningsSetup, PlayerSummary, TeamSummary


NormalRun = Literal[0, 1, 2, 3, 4, 6]


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: NormalRun


class BowlerChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bowler_id: UUID


class NextInningsCreate(OpeningInningsSetup):
    """Openers for the next innings; same rules as the first innings setup."""


class DeliveryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    sequence: int
    over_number: int
    ball_number: int
    striker: PlayerSummary
    non_striker: PlayerSummary
    bowler: PlayerSummary
    batter_runs: int
    extra_runs: int
    total_runs: int

    is_legal_ball: bool
    recorded_at: datetime


class InningsSummary(BaseModel):
    innings_number: int
    status: InningsStatus
    batting_team: TeamSummary
    total_runs: int
    wickets: int
    legal_balls: int
    overs: str


class ScoringStateRead(BaseModel):
    match_id: UUID
    innings_id: UUID
    innings_number: int
    match_status: MatchStatus
    innings_status: InningsStatus
    batting_team: TeamSummary
    bowling_team: TeamSummary
    total_runs: int
    wickets: int
    legal_balls: int
    completed_overs: int
    balls_in_current_over: int
    overs: str
    current_run_rate: float
    total_overs: int | None
    balls_per_over: int
    overs_complete: bool
    striker: PlayerSummary
    non_striker: PlayerSummary
    current_bowler: PlayerSummary
    next_sequence: int
    next_over_number: int
    next_ball_number: int
    at_over_boundary: bool
    # True when an over has just finished and the
    # bowler of that over is still selected. No
    # delivery can be recorded until it changes.
    bowler_change_required: bool
    previous_over_bowler_id: UUID | None
    recent_deliveries: list[DeliveryRead]

    innings: list[InningsSummary]
    innings_complete: bool
    can_end_innings: bool
    can_start_next_innings: bool
    next_innings_number: int | None
    next_batting_team: TeamSummary | None
    next_bowling_team: TeamSummary | None
    # Only set in the final innings.
    target: int | None
    runs_required: int | None
    balls_remaining: int | None
    result_summary: str | None

    # State returned by this API is always
    # rebuilt from delivery history.
    # This only verifies the optional
    # cached innings values.
    cache_matches_history: bool


