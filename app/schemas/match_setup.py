from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    InningsStatus,
    MatchStatus,
    MatchType,
    PlayerRole,
    TossDecision,
)


def strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class MatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=180)
    match_number: int | None = Field(default=None, ge=1)

    team_a_id: UUID
    team_b_id: UUID
    tournament_id: UUID | None = None
    venue_id: UUID | None = None

    match_type: MatchType = MatchType.OTHER

    # No upper limits are imposed.
    # Minimums below are structural only.
    players_per_side: int = Field(default=11, ge=2)

    # None means unlimited overs.
    total_overs: int | None = Field(
        default=None,
        ge=1,
    )

    balls_per_over: int = Field(
        default=6,
        ge=1,
    )

    innings_per_team: int = Field(
        default=1,
        ge=1,
    )

    scheduled_at: datetime | None = None

    _strip_title = field_validator(
        "title",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_teams(self) -> Self:
        if self.team_a_id == self.team_b_id:
            raise ValueError(
                "Team A and Team B must be different"
            )

        return self


class MatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=180)
    match_number: int | None = Field(default=None, ge=1)
    team_a_id: UUID | None = None
    team_b_id: UUID | None = None
    tournament_id: UUID | None = None
    venue_id: UUID | None = None
    match_type: MatchType | None = None
    players_per_side: int | None = Field(default=None, ge=2)
    total_overs: int | None = Field(default=None, ge=1)
    balls_per_over: int | None = Field(default=None, ge=1)
    innings_per_team: int | None = Field(default=None, ge=1)
    scheduled_at: datetime | None = None

    _strip_title = field_validator(
        "title",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one match field must be supplied")

        if (
            self.team_a_id is not None
            and self.team_b_id is not None
            and self.team_a_id == self.team_b_id
        ):
            raise ValueError("Team A and Team B must be different")

        return self


class TossSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner_team_id: UUID
    decision: TossDecision


class PlayingTeamPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID
    batting_order: int = Field(ge=1)
    is_captain: bool = False
    is_wicket_keeper: bool = False



class PlayingTeamSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No maximum team size.
    # Match.players_per_side decides the required count.
    players: list[PlayingTeamPlayer] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_playing_team(self) -> Self:
        player_ids = [
            item.player_id
            for item in self.players
        ]

        batting_orders = [
            item.batting_order
            for item in self.players
        ]

        count = len(self.players)

        if len(set(player_ids)) != count:
            raise ValueError(
                "Playing team must contain unique players"
            )

        if set(batting_orders) != set(range(1, count + 1)):
            raise ValueError(
                "Batting order must contain every "
                f"number from 1 through {count} "
                "exactly once"
            )

        return self


class OpeningInningsSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    striker_id: UUID
    non_striker_id: UUID
    opening_bowler_id: UUID

    @model_validator(mode="after")
    def validate_openers(self) -> Self:
        if self.striker_id == self.non_striker_id:
            raise ValueError(
                "Striker and non-striker "
                "must be different players"
            )

        return self


class TeamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    short_name: str
    code: str


class VenueSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    city: str
    country: str | None


class TournamentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    season: str | None


class PlayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    short_name: str | None


class SquadPlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_player_id: UUID
    player: PlayerSummary
    role: PlayerRole
    squad_number: int | None


class MatchPlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    player: PlayerSummary
    batting_order: int | None
    role: PlayerRole
    is_captain: bool
    is_wicket_keeper: bool


class InningsSetupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    innings_number: int
    batting_team: TeamSummary
    bowling_team: TeamSummary
    status: InningsStatus
    striker: PlayerSummary | None
    non_striker: PlayerSummary | None
    current_bowler: PlayerSummary | None


class MatchReadinessRead(BaseModel):
    details_complete: bool
    toss_complete: bool
    team_a_players_complete: bool
    team_b_players_complete: bool
    opening_innings_complete: bool
    ready: bool
    missing: list[str]


class MatchListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    match_number: int | None
    team_a: TeamSummary
    team_b: TeamSummary
    tournament: TournamentSummary | None
    venue: VenueSummary | None
    match_type: MatchType
    players_per_side: int
    total_overs: int | None
    balls_per_over: int
    innings_per_team: int
    scheduled_at: datetime | None
    status: MatchStatus
    created_at: datetime
    updated_at: datetime


class MatchSetupRead(MatchListRead):
    toss_winner: TeamSummary | None
    toss_decision: TossDecision | None
    players: list[MatchPlayerRead]
    innings: list[InningsSetupRead]
    readiness: MatchReadinessRead


class SquadMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: UUID
    role: PlayerRole = PlayerRole.BATTER
    squad_number: int | None = Field(default=None, ge=1)


class TeamSquadMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    team_id: UUID
    player: PlayerSummary
    role: PlayerRole
    squad_number: int | None
    is_active: bool