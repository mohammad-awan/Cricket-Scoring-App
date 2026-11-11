from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==================================================
# BASE SCHEMA
# ==================================================

class FixtureSchema(BaseModel):
    """Base configuration for fixture API schemas."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ==================================================
# TYPE DEFINITIONS
# ==================================================
FixtureMethod = Literal[
    "manual",
    "random",
    "round_robin",
    "knockout",
]
FixtureStatus = Literal[
    "draft",
    "published",
    "postponed",
    "cancelled",
    "completed",
]
GenerationStatus = Literal["draft", "published", "cancelled"]
AdvancementType = Literal["winner", "loser"]
BracketSide = Literal["home", "away"]


# ==================================================
# SHARED VALIDATION
# ==================================================

def validate_fixture_times(scheduled_at: datetime | None, ends_at: datetime | None) -> None:
    """Validate a fixture's start and end times."""

    if scheduled_at is None or ends_at is None:
        return

    if (
        scheduled_at.tzinfo is None
        or scheduled_at.utcoffset() is None
        or ends_at.tzinfo is None
        or ends_at.utcoffset() is None
    ):
        raise ValueError("Fixture scheduling times must include a timezone.")

    if ends_at <= scheduled_at:
        raise ValueError("Fixture end time must be after start time.")


def validate_fixture_teams(home_team_id: UUID | None, away_team_id: UUID | None) -> None:
    """Prevent a team from playing against itself."""

    if (
        home_team_id is not None
        and away_team_id is not None
        and home_team_id == away_team_id
    ):
        raise ValueError("Home and away teams must be different.")


# ==================================================
# FIXTURE GENERATION
# ==================================================

class FixtureGenerationRequest(FixtureSchema):
    """
    Tournament fixture generation request.

    Retained for compatibility with the existing
    tournament fixture schemas.
    """

    tournament_id: UUID
    method: FixtureMethod
    seed: int | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)


class FixtureGenerationResponse(FixtureSchema):
    """Database representation of a generation run."""

    id: UUID
    tournament_id: UUID
    method: FixtureMethod
    status: GenerationStatus
    seed: int | None = None
    algorithm_version: str
    configuration: dict[str, Any]
    created_at: datetime
    published_at: datetime | None = None


class FixtureGenerateRequest(FixtureSchema):
    """
    Request body for:

    POST /fixtures/tournaments/{tournament_id}/generate

    Tournament ID is supplied in the URL.
    """

    method: FixtureMethod
    configuration: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None


class FixtureGenerationResultResponse(FixtureSchema):
    """Result returned after generating fixtures."""

    generation_run_id: UUID
    tournament_id: UUID
    fixture_count: int = Field(ge=0)
    round_count: int = Field(ge=0)


# ==================================================
# FIXTURE ROUNDS
# ==================================================

class FixtureRoundCreate(FixtureSchema):
    """Create a fixture round."""

    tournament_id: UUID
    generation_run_id: UUID
    round_number: int = Field(ge=1)
    stage: str = Field(
        default="league",
        min_length=1,
        max_length=40,
    )
    name: str | None = Field(
        default=None,
        max_length=100,
    )


class FixtureRoundResponse(FixtureRoundCreate):
    """Fixture round database response."""

    id: UUID
    created_at: datetime


# ==================================================
# FIXTURE CREATION
# ==================================================

class FixtureCreate(FixtureSchema):
    """Schema for creating an individual fixture."""

    tournament_id: UUID
    generation_run_id: UUID
    round_id: UUID
    fixture_number: int = Field(ge=1)
    home_team_id: UUID | None = None
    away_team_id: UUID | None = None
    venue_id: UUID | None = None
    scheduled_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_fixture(self):
        validate_fixture_teams(self.home_team_id, self.away_team_id)
        validate_fixture_times(self.scheduled_at, self.ends_at)

        return self


# ==================================================
# FIXTURE UPDATE
# ==================================================

class FixtureUpdateRequest(FixtureSchema):
    """
    Request body for updating an existing fixture.

    Uses optimistic concurrency control through
    expected_version.

    Only explicitly provided fields are passed
    to the service.
    """

    expected_version: int = Field(ge=1)
    home_team_id: UUID | None = None
    away_team_id: UUID | None = None
    venue_id: UUID | None = None
    scheduled_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_changes(self):

        changed_fields = (
            self.model_fields_set
            - {"expected_version"}
        )

        if not changed_fields:
            raise ValueError("At least one fixture field must be supplied.")

        # Validate fields when both values are supplied.
        # The service must validate the merged values
        # for partial updates.

        if (
            "home_team_id" in changed_fields
            and "away_team_id" in changed_fields
        ):
            validate_fixture_teams(
                self.home_team_id,
                self.away_team_id,
            )

        if (
            "scheduled_at" in changed_fields
            and "ends_at" in changed_fields
        ):
            validate_fixture_times(
                self.scheduled_at,
                self.ends_at,
            )

        return self


# ==================================================
# FIXTURE RESPONSE
# ==================================================

class FixtureResponse(FixtureCreate):
    """Complete fixture response from the database."""

    id: UUID
    status: FixtureStatus
    is_locked: bool
    version: int = Field(ge=1)
    match_id: UUID | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FixtureListResponse(FixtureSchema):
    """Paginated tournament fixture list."""

    tournament_id: UUID
    total: int = Field(ge=0)
    fixtures: list[FixtureResponse] = Field(default_factory=list)


# ==================================================
# KNOCKOUT BRACKET DEPENDENCIES
# ==================================================

class BracketDependencyCreate(FixtureSchema):
    """Define the source of a knockout bracket slot."""

    fixture_id: UUID
    source_fixture_id: UUID
    target_side: BracketSide
    advancement: AdvancementType = "winner"

    @model_validator(mode="after")
    def validate_dependency(self):

        if self.fixture_id == self.source_fixture_id:
            raise ValueError("A fixture cannot depend on itself.")

        return self


class BracketDependencyResponse(BracketDependencyCreate):
    """Knockout bracket dependency response."""

    id: UUID


# ==================================================
# VENUE AVAILABILITY
# ==================================================

class VenueAvailabilityCreate(FixtureSchema):
    """Venue availability configuration."""

    tournament_id: UUID
    venue_id: UUID
    start_at: datetime
    end_at: datetime
    is_available: bool = True

    @model_validator(mode="after")
    def validate_time_range(self):

        if (
            self.start_at.tzinfo is None
            or self.start_at.utcoffset() is None
            or self.end_at.tzinfo is None
            or self.end_at.utcoffset() is None
        ):
            raise ValueError("Venue availability times must include a timezone.")

        if self.end_at <= self.start_at:
            raise ValueError("Availability end must be after start.")

        return self


class VenueAvailabilityResponse(VenueAvailabilityCreate):
    """Venue availability database response."""

    id: UUID
    created_at: datetime


# ==================================================
# SCHEDULING CONSTRAINTS
# ==================================================

class SchedulingConstraintCreate(FixtureSchema):
    """Tournament scheduling constraint."""

    tournament_id: UUID
    name: str = Field(min_length=1, max_length=100)
    configuration: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SchedulingConstraintResponse(SchedulingConstraintCreate):
    """Scheduling constraint database response."""

    id: UUID
    created_at: datetime


# ==================================================
# FIXTURE AUDIT HISTORY
# ==================================================

class FixtureChangeAuditResponse(FixtureSchema):
    """Audit history for changes to a fixture."""

    id: UUID
    fixture_id: UUID
    action: str
    # Database model stores actor_id as a string.
    actor_id: str | None = None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    reason: str | None = None
    created_at: datetime


# ==================================================
# FIXTURE PUBLICATION
# ==================================================

class FixturePublishRequest(FixtureSchema):
    """
    Request body for:

    POST /fixtures/generations/{generation_run_id}/publish

    Generation run ID is supplied in the URL.
    """
    expected_fixture_count: int = Field(ge=1)


class FixturePublishResponse(FixtureSchema):
    """Response after successful fixture publication."""

    generation_run_id: UUID
    published_count: int = Field(ge=0)
    status: Literal["published"] = "published"


# ==================================================
# SCHEDULE GENERATION
# ==================================================

class FixtureScheduleRequest(FixtureSchema):
    """Request to schedule generated fixtures."""

    tournament_id: UUID
    generation_run_id: UUID
    duration_minutes: int = Field(gt=0)
    minimum_rest_minutes: int = Field(ge=0, default=0)


class FixtureScheduleResponse(FixtureSchema):
    """Result of fixture scheduling."""

    generation_run_id: UUID
    scheduled_count: int = Field(ge=0)
    unscheduled_count: int = Field(ge=0)
    conflicts: list[str] = Field(default_factory=list)
