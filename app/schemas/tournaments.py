from __future__ import annotations
from datetime import date, datetime
from typing import Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import TournamentStatus
from app.schemas.common import strip_required_text, strip_text
from app.domain.tournament_rules import TournamentRules


class TournamentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    season: str | None = Field(default=None, max_length=40)
    organizer: str | None = Field(default=None, max_length=160)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    _strip_text = field_validator(
        "name",
        "slug",
        "season",
        "organizer",
        "description",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be on or after start_date")

        return self


class TournamentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    season: str | None = Field(default=None, max_length=40)
    organizer: str | None = Field(default=None, max_length=160)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    _strip_required = field_validator(
        "name",
        mode="before",
    )(strip_required_text)

    _strip_optional = field_validator(
        "slug",
        "season",
        "organizer",
        "description",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(
                "At least one tournament field must be supplied"
            )

        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be on or after start_date")

        return self


class TournamentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    season: str | None
    organizer: str | None
    description: str | None
    start_date: date | None
    end_date: date | None
    status: TournamentStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompetitionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=40)
    sponsor: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    geographic_scope: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=160)
    timezone: str = Field(default="UTC", max_length=80)
    website: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)
    terms: str | None = None
    trophy_name: str | None = Field(default=None, max_length=160)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    expected_teams: int | None = Field(default=None, ge=2)
    minimum_teams: int = Field(default=2, ge=2)
    maximum_teams: int | None = Field(default=None, ge=2)
    reserve_team_limit: int = Field(default=0, ge=0)
    registration_mode: str = Field(default="open", pattern="^(open|invitational)$")
    entry_requires_approval: bool = True
    roster_lock_at: datetime | None = None
    replacement_cutoff_at: datetime | None = None
    primary_venue_id: UUID | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Invalid IANA timezone") from error

        return value

    @model_validator(mode="after")
    def validate_config(self):
        if (
            self.maximum_teams is not None
            and self.maximum_teams < self.minimum_teams
        ):
            raise ValueError("Maximum teams must be >= minimum teams")

        if (
            self.expected_teams is not None
            and (
                self.expected_teams < self.minimum_teams
                or (
                    self.maximum_teams is not None
                    and self.expected_teams > self.maximum_teams
                )
            )
        ):
            raise ValueError("Expected teams must fit registration limits")

        if (
            self.registration_opens_at
            and self.registration_closes_at
            and (
                self.registration_closes_at
                <= self.registration_opens_at
            )
        ):
            raise ValueError("Registration close must follow opening")

        for value in (
            self.registration_opens_at,
            self.registration_closes_at,
            self.roster_lock_at,
            self.replacement_cutoff_at,
        ):
            if value is not None and value.utcoffset() is None:
                raise ValueError(
                    "Registration and lock times "
                    "must include timezone offsets"
                )

        return self


def _require_aware(*values: datetime | None) -> None:
    for value in values:
        if value is not None and value.utcoffset() is None:
            raise ValueError(
                "Registration and lock times "
                "must include timezone offsets"
            )


class CompetitionConfigUpdate(BaseModel):
    """PATCH payload: only supplied fields change.

    Cross-field rules are checked by the service against the merged
    (stored + supplied) configuration using CompetitionConfig.
    """

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=40)
    sponsor: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    geographic_scope: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=160)
    timezone: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)
    terms: str | None = None
    trophy_name: str | None = Field(default=None, max_length=160)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    expected_teams: int | None = Field(default=None, ge=2)
    minimum_teams: int | None = Field(default=None, ge=2)
    maximum_teams: int | None = Field(default=None, ge=2)
    reserve_team_limit: int | None = Field(default=None, ge=0)
    registration_mode: str | None = Field(
        default=None,
        pattern="^(open|invitational)$",
    )
    entry_requires_approval: bool | None = None
    roster_lock_at: datetime | None = None
    replacement_cutoff_at: datetime | None = None
    primary_venue_id: UUID | None = None

    _strip_text = field_validator(
        "code",
        "sponsor",
        "category",
        "geographic_scope",
        "location",
        "timezone",
        "website",
        "contact_email",
        "contact_phone",
        "terms",
        "trophy_name",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(
                "At least one configuration field must be supplied"
            )

        _require_aware(
            self.registration_opens_at,
            self.registration_closes_at,
            self.roster_lock_at,
            self.replacement_cutoff_at,
        )
        return self


class TournamentDetailRead(TournamentRead):
    """Expanded Stage 11 view; TournamentRead stays unchanged for
    existing master-data clients."""

    code: str | None
    sponsor: str | None
    category: str | None
    geographic_scope: str | None
    location: str | None
    timezone: str
    website: str | None
    contact_email: str | None
    contact_phone: str | None
    terms: str | None
    trophy_name: str | None
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    expected_teams: int | None
    minimum_teams: int
    maximum_teams: int | None
    reserve_team_limit: int
    registration_mode: str
    entry_requires_approval: bool
    roster_lock_at: datetime | None
    replacement_cutoff_at: datetime | None
    is_published: bool
    primary_venue_id: UUID | None


class RuleVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: TournamentRules
    created_by: str | None = Field(default=None, max_length=160)


class RuleVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    version: int
    format_code: str
    competition_structure: str
    rules: dict
    checksum: str
    created_at: datetime


class TournamentTeamRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: UUID
    display_name: str | None = Field(default=None, max_length=160)
    seed: int | None = Field(default=None, ge=1)
    manager_name: str | None = Field(default=None, max_length=160)
    is_reserve: bool = False

    _strip_text = field_validator(
        "display_name",
        "manager_name",
        mode="before",
    )(strip_text)


class TournamentTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    team_id: UUID
    display_name: str | None
    seed: int | None
    registration_status: str
    is_reserve: bool
    captain_player_id: UUID | None
    manager_name: str | None
    group_id: UUID | None


class RegistrationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    reason: str | None = Field(default=None, max_length=500)


class RosterAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID
    role: str = Field(
        default="batter",
        pattern="^(batter|bowler|all_rounder|wicket_keeper)$",
    )


class RosterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_team_id: UUID
    player_id: UUID
    role: str
    is_available: bool
    locked_at: datetime | None


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)

    _strip_name = field_validator("name", mode="before")(strip_required_text)


class GroupAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: UUID | None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: TournamentStatus
    reason: str | None = Field(default=None, max_length=1000)


class RulePropagationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apply_to_unstarted: bool = False
    expected_previous_version: int = Field(ge=1)


class VenueAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue_id: UUID


class TournamentPreview(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    registered_teams: int
    approved_teams: int
    current_rules_version: int | None


class TournamentPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publish: bool


class TournamentWithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)


class TournamentRosterAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_available: bool
    reason: str | None = Field(default=None, max_length=500)


class TournamentCaptainUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID


class TournamentRosterLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class TournamentGroupAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: UUID | None


class TournamentRulesPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: TournamentRules


class TournamentRuleValidationRead(BaseModel):
    valid: bool
    errors: list[str]


class TournamentAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    event_type: str
    actor_id: str | None
    details: dict
    created_at: datetime


class TournamentGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    name: str
    sort_order: int
    created_at: datetime


class TournamentVenueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    venue_id: UUID


class RulePropagationRead(BaseModel):
    rules_version: int
    updated_match_ids: list[UUID]
    skipped_match_ids: list[UUID]


class TournamentTransitionsRead(BaseModel):
    current: TournamentStatus
    allowed: list[TournamentStatus]
    reason_required: list[TournamentStatus]
