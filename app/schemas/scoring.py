from __future__ import annotations
from datetime import datetime
from typing import Literal, Self
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from app.models.enums import DeliveryStatus, InningsStatus, MatchStatus, WicketType
from app.schemas.match_setup import OpeningInningsSetup, PlayerSummary, TeamSummary


NormalRun = Literal[0, 1, 2, 3, 4, 6]
WicketEnd = Literal["striker_end", "non_striker_end"]


class WicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wicket_type: WicketType
    dismissed_player_id: UUID
    fielder_id: UUID | None = None
    next_batter_id: UUID | None = None
    # Useful for exact run-out
    # end reconstruction.
    wicket_end: WicketEnd | None = None

    @model_validator(mode="after")
    def validate_wicket_end(self) -> Self:
        if self.wicket_end is not None and self.wicket_type != WicketType.RUN_OUT:
            raise ValueError(
                "wicket_end is only "
                "valid for a run out"
            )

        return self


class DeliveryCreate(BaseModel):
    """
    One official scoring event.
    runs = batter runs.
    A no-ball contributes exactly
    one automatic extra.
    wide_runs is the complete wide
    total, including the automatic
    wide.
    """

    model_config = ConfigDict(extra="forbid")

    runs: NormalRun = 0
    wide_runs: int = Field(default=0, ge=0)
    no_ball: bool = False
    bye_runs: int = Field(default=0, ge=0)
    leg_bye_runs: int = Field(default=0, ge=0)
    wicket: WicketCreate | None = None

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        if self.wide_runs > 0:

            if (
                self.no_ball
                or self.runs > 0
                or self.bye_runs > 0
                or self.leg_bye_runs > 0
            ):

                raise ValueError(
                    "A wide cannot also "
                    "contain batter runs, "
                    "a no-ball, byes or "
                    "leg byes"
                )

        if self.bye_runs > 0 and self.leg_bye_runs > 0:
            raise ValueError(
                "A delivery cannot "
                "be both a bye and "
                "a leg bye"
            )

        if (
            (
                self.bye_runs > 0
                or self.leg_bye_runs > 0
            )
            and self.runs > 0
        ):

            raise ValueError(
                "Batter runs cannot "
                "be combined with "
                "byes or leg byes"
            )

        if self.no_ball and self.wide_runs > 0:
            raise ValueError(
                "A delivery cannot "
                "be both a no-ball "
                "and a wide"
            )

        return self


class DeliveryUndo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError(
                "Correction reason "
                "must be at least "
                "3 characters"
            )

        return value


class BowlerChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bowler_id: UUID


class NextInningsCreate(OpeningInningsSetup):
    """
    Uses the same participant
    validation contract as the
    first innings.
    """


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
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    total_runs: int
    is_legal_ball: bool
    wicket_type: WicketType | None
    dismissed_player: PlayerSummary | None
    fielder: PlayerSummary | None 
    next_batter: PlayerSummary | None
    status: DeliveryStatus
    correction_reason: str | None = None
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
    max_wickets: int
    all_out: bool
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
    dismissed_player_ids: list[UUID]
    next_sequence: int
    next_over_number: int
    next_ball_number: int
    at_over_boundary: bool
    bowler_change_required: bool
    previous_over_bowler_id: UUID | None
    # Both active and void events
    # are returned here so the
    # correction audit is visible.
    recent_deliveries: list[DeliveryRead]
    innings: list[InningsSummary]
    innings_complete: bool
    can_end_innings: bool
    can_start_next_innings: bool
    next_innings_number: int | None
    next_batting_team: TeamSummary | None
    next_bowling_team: TeamSummary | None 
    target: int | None
    runs_required: int | None
    balls_remaining: int | None
    result_summary: str | None
    cache_matches_history: bool