from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models.enums import InningsStatus, MatchStatus
from app.schemas.match_setup import PlayerSummary, TeamSummary


class BattingScorecardRow(BaseModel):
    player: PlayerSummary
    batting_position: int | None
    dismissal: str
    is_not_out: bool
    runs: int
    balls: int
    fours: int
    sixes: int
    strike_rate: float


class BowlingScorecardRow(BaseModel):
    player: PlayerSummary
    overs: str
    legal_balls: int
    maidens: int
    runs_conceded: int
    wickets: int
    wides: int
    no_balls: int
    economy: float


class PartnershipRead(BaseModel):
    number: int
    wicket_number: int | None
    batter_one: PlayerSummary
    batter_two: PlayerSummary
    runs: int
    legal_balls: int


class ExtrasRead(BaseModel):
    total: int
    wides: int
    no_balls: int
    byes: int
    leg_byes: int


class InningsScorecardRead(BaseModel):
    innings_id: UUID
    innings_number: int
    status: InningsStatus
    batting_team: TeamSummary
    bowling_team: TeamSummary
    total_runs: int
    wickets: int
    legal_balls: int
    overs: str
    run_rate: float
    extras: ExtrasRead
    batting: list[BattingScorecardRow]
    bowling: list[BowlingScorecardRow]
    partnerships: list[PartnershipRead]


class ChaseRead(BaseModel):
    target: int | None
    runs_required: int | None
    balls_remaining: int | None
    required_run_rate: float | None


class MatchResultRead(BaseModel):
    completed: bool
    winner_team: TeamSummary | None
    result_type: str | None
    result_margin: int | None
    summary: str | None
    completed_at: datetime | None


class MatchLifecycleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: UUID
    status: MatchStatus
    current_innings_number: int | None
    state_label: str
    can_score: bool
    can_start_next_innings: bool
    chase: ChaseRead
    result: MatchResultRead



class FullScorecardRead(BaseModel):
    match_id: UUID
    title: str | None
    status: MatchStatus
    team_a: TeamSummary
    team_b: TeamSummary
    total_overs: int | None
    balls_per_over: int
    innings_per_team: int
    innings: list[InningsScorecardRead]
    lifecycle: MatchLifecycleRead

