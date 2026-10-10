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
from app.schemas.retirements import BatterSelectionMode, RetirementRead


NormalRun = Literal[0, 1, 2, 3, 4, 6]
WicketEnd = Literal["striker_end", "non_striker_end"]



class WicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wicket_type: WicketType
    # Optional: auto-derived for striker-only wickets.
    # Explicit ID is retained for run-out and
    # obstructing-field situations.
    dismissed_player_id: UUID | None = None
    fielder_id: UUID | None = None
    # Default batting order or scorer override.
    selection_mode: BatterSelectionMode = "automatic"
    # Required for a manual override when another
    # batter is eligible to enter.
    next_batter_id: UUID | None = None
    wicket_end: WicketEnd | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.selection_mode == "automatic" and self.next_batter_id is not None:
            raise ValueError("next_batter_id must be omitted in automatic selection mode.")

        if self.wicket_end is not None and self.wicket_type != WicketType.RUN_OUT:
            raise ValueError("wicket_end is only valid for run out.")

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
    client_event_id: UUID | None = None
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
    # Includes retired-out batters.
    dismissed_player_ids: list[UUID]
    # Retired hurt and eligible to resume.
    retired_hurt_player_ids: list[UUID] = Field(default_factory=list)
    retired_out_player_ids: list[UUID] = Field(default_factory=list)
    # Official retirements in event order.
    retirements: list[RetirementRead] = Field(default_factory=list)
    # True when the latest official event is a
    # retirement; it must be undone before the
    # preceding delivery can be.
    retirement_blocks_undo: bool = False
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