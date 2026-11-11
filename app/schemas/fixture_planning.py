"""Typed inputs for the Stage 12 fixture workspace."""
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PlanningSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlackoutInput(PlanningSchema):
    start_at: AwareDatetime
    end_at: AwareDatetime
    venue_id: UUID | None = None
    team_id: UUID | None = None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_at <= self.start_at or (self.venue_id and self.team_id):
            raise ValueError("Blackouts need an increasing interval and at most one target.")
        return self


class ManualPairing(PlanningSchema):
    round_number: int = Field(ge=1)
    home_team_id: UUID
    away_team_id: UUID
    leg: int = Field(default=1, ge=1, le=2)
    venue_id: UUID | None = None
    scheduled_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_pair(self):
        if self.home_team_id == self.away_team_id:
            raise ValueError("A team cannot play itself.")
        if self.ends_at and (not self.scheduled_at or self.ends_at <= self.scheduled_at):
            raise ValueError("End time must follow the start time.")
        return self


class FixturePlanRequest(PlanningSchema):
    method: Literal["manual", "random", "round_robin", "knockout"] = "round_robin"
    format: Literal["round_robin", "knockout", "groups", "hybrid"] = "round_robin"
    team_ids: list[UUID] = Field(default_factory=list, max_length=128)
    legs: Literal[1, 2] = 1
    overs: int | None = Field(default=None, ge=1)
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    group_count: int = Field(default=2, ge=2, le=16)
    groups: dict[str, list[UUID]] = Field(default_factory=dict)
    seed_pots: list[list[UUID]] = Field(default_factory=list)
    advance_per_group: int = Field(default=2, ge=1, le=4)
    pairings: list[ManualPairing] = Field(default_factory=list, max_length=5000)
    venue_ids: list[UUID] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    final_date: date | None = None
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    times: list[time] = Field(default_factory=lambda: [time(10), time(14)])
    duration_minutes: int = Field(default=180, ge=1, le=1440)
    minimum_rest_minutes: int = Field(default=60, ge=0, le=43200)
    blackouts: list[BlackoutInput] = Field(default_factory=list, max_length=500)
    auto_schedule: bool = True
    request_id: UUID | None = None

    @model_validator(mode="after")
    def valid_config(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select a valid IANA timezone.")
        if len(self.team_ids) != len(set(self.team_ids)):
            raise ValueError("Team selections must be unique.")
        if any(not name.strip() or ":" in name or len(name) > 40 for name in self.groups):
            raise ValueError("Group names must be 1–40 characters and cannot contain a colon.")
        if not self.weekdays or not set(self.weekdays) <= set(range(7)):
            raise ValueError("Choose playable weekdays (Monday = 0).")
        if len(self.times) > 24 or any(value.tzinfo for value in self.times):
            raise ValueError("Use at most 24 local start times without offsets.")
        if self.start_date and self.end_date:
            if self.end_date < self.start_date or (self.end_date - self.start_date).days > 730:
                raise ValueError("The scheduling window must span between 0 and 730 days.")
        if self.final_date and ((self.start_date and self.final_date < self.start_date) or
                                (self.end_date and self.final_date > self.end_date)):
            raise ValueError("The final date must lie in the scheduling window.")
        if self.method == "random" and self.seed is None:
            raise ValueError("Record a seed for a reproducible random draw.")
        if self.method == "manual" and self.format != "round_robin":
            raise ValueError("The manual editor defines a round-robin draw.")
        return self


class FixturePlanSave(FixturePlanRequest):
    request_id: UUID


class FixtureChange(PlanningSchema):
    fixture_id: UUID
    expected_version: int = Field(ge=1)
    home_team_id: UUID | None = None
    away_team_id: UUID | None = None
    venue_id: UUID | None = None
    scheduled_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class FixtureEditBatch(PlanningSchema):
    changes: list[FixtureChange] = Field(min_length=1, max_length=5000)
    reason: str = Field(min_length=1, max_length=1000)


class FixtureAction(PlanningSchema):
    expected_version: int = Field(ge=1)
    action: Literal["lock", "unlock", "postpone", "cancel", "reschedule", "review"]
    reason: str = Field(min_length=1, max_length=1000)
    scheduled_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    venue_id: UUID | None = None


class FixtureConfirm(PlanningSchema):
    expected_versions: dict[UUID, int] = Field(min_length=1)
    reason: str = Field(default="Organizer confirmed fixture publication", min_length=1, max_length=1000)


class FixtureRegenerate(PlanningSchema):
    expected_versions: dict[UUID, int] = Field(min_length=1)
    configuration: FixturePlanRequest

