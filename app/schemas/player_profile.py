from __future__ import annotations
from datetime import date,  datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models.enums import (
    BattingHand,
    BowlingArm,
    BowlingStyle,
    PlayerRole,
    PlayerStatus,
)


class PlayerIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    short_name: str | None
    date_of_birth: date | None
    age: int | None
    nationality: str | None
    external_id: str | None
    status: PlayerStatus
    batting_hand: BattingHand | None
    bowling_arm: BowlingArm | None
    bowling_style: BowlingStyle | None
    batting_style_display: str | None
    bowling_style_display: str | None


class PlayerTeamMembershipRead(BaseModel):
    team_id: UUID
    team_name: str
    team_short_name: str
    role: PlayerRole
    squad_number: int | None
    joined_on: date | None
    left_on: date | None
    is_active: bool


class RecentBattingInningsRead(BaseModel):
    match_id: UUID
    innings_id: UUID
    innings_number: int
    runs: int
    balls_faced: int
    not_out: bool


class RecentBowlingInningsRead(BaseModel):
    match_id: UUID
    innings_id: UUID
    innings_number: int
    wickets: int
    runs_conceded: int
    balls_bowled: int


class BattingCareerRead(BaseModel):
    matches: int
    innings: int
    runs: int
    balls_faced: int
    not_outs: int
    dismissals: int
    highest_score: int
    highest_score_not_out: bool
    average: float | None
    strike_rate: float | None
    fours: int
    sixes: int
    recent_form: list[RecentBattingInningsRead]


class BowlingCareerRead(BaseModel):
    matches: int
    innings: int
    balls_bowled: int
    overs: float
    runs_conceded: int
    wickets: int
    economy: float | None
    average: float | None
    strike_rate: float | None
    best_wickets: int
    best_runs: int
    best_figures: str | None
    recent_form: list[RecentBowlingInningsRead]


class PlayerCareerRead(BaseModel):
    batting: BattingCareerRead
    bowling: BowlingCareerRead


class MatchBattingFigureRead(BaseModel):
    innings_id: UUID
    innings_number: int
    runs: int
    balls_faced: int
    fours: int
    sixes: int
    not_out: bool


class MatchBowlingFigureRead(BaseModel):
    innings_id: UUID
    innings_number: int
    balls_bowled: int
    overs: float
    runs_conceded: int
    wickets: int
    economy: float | None


class PlayerMatchHistoryRead(BaseModel):
    match_id: UUID
    title: str | None
    match_date: datetime
    scheduled_at: datetime | None
    player_team_id: UUID
    player_team_name: str
    opponent_team_id: UUID
    opponent_team_name: str
    batting: list[MatchBattingFigureRead]
    bowling: list[MatchBowlingFigureRead]


class PlayerMatchHistoryPageRead(BaseModel):
    items: list[PlayerMatchHistoryRead]
    page: int
    page_size: int
    total: int
    pages: int


class PlayerProfileRead(BaseModel):
    player: PlayerIdentityRead
    active_teams: list[PlayerTeamMembershipRead]
    career: PlayerCareerRead
    recent_matches: list[PlayerMatchHistoryRead]