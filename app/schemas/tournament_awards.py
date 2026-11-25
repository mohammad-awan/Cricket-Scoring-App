from __future__ import annotations
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AwardWeights(BaseModel):
    """Transparent Player of the Tournament weighting.

    Every component is normalized to 0..1 across eligible candidates
    before weighting, so weights express relative importance directly.
    """

    model_config = ConfigDict(extra="forbid")

    runs: float = Field(default=0.30, ge=0)
    batting_efficiency: float = Field(default=0.15, ge=0)
    wickets: float = Field(default=0.30, ge=0)
    economy: float = Field(default=0.10, ge=0)
    fielding: float = Field(default=0.15, ge=0)
    minimum_matches: int = Field(default=1, ge=1)
    min_batting_balls: int = Field(default=30, ge=0)
    min_bowling_balls: int = Field(default=60, ge=0)

    @model_validator(mode="after")
    def validate_weights(self):
        if self.runs + self.batting_efficiency + self.wickets + self.economy + self.fielding == 0:
            raise ValueError("At least one award weight must be positive")
        return self


class EmergingEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Age on the reference date (defaults to the tournament start date).
    max_age: int | None = Field(default=None, ge=5, le=60)
    born_on_or_after: date | None = None
    reference_date: date | None = None

    @property
    def configured(self) -> bool:
        return self.max_age is not None or self.born_on_or_after is not None


class AwardSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: AwardWeights = Field(default_factory=AwardWeights)
    emerging: EmergingEligibility = Field(default_factory=EmergingEligibility)
    batting_min_innings: int = Field(default=0, ge=0)
    min_economy_balls: int = Field(default=60, ge=0)
    voting_enabled: bool = False
    committee: list[str] = Field(default_factory=list, max_length=50)
    candidates_limit: int = Field(default=5, ge=1, le=50)


class AwardSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: AwardSettings
    reason: str = Field(min_length=10, max_length=2000)


class AwardConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID | None = None
    team_id: UUID | None = None
    # organizer_selection: manual choice (an override when it differs from
    # the computed leader); statistical_leader: confirm the unambiguous
    # computed leader; committee_vote: confirm the unique vote winner.
    basis: Literal["organizer_selection", "statistical_leader", "committee_vote"] = "organizer_selection"
    reason: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_recipient(self):
        if (self.player_id is None) == (self.team_id is None):
            raise ValueError("Specify exactly one award recipient")
        return self


class AwardRevocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=2000)


class AwardVote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voter: str = Field(min_length=1, max_length=160)
    player_id: UUID | None = None
    team_id: UUID | None = None
    score: int = Field(default=1, ge=1, le=100)
    reason: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_recipient(self):
        if (self.player_id is None) == (self.team_id is None):
            raise ValueError("Specify exactly one vote recipient")
        return self


class PlayerOfMatchConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID
    reason: str = Field(min_length=10, max_length=2000)


class AwardPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=2000)
