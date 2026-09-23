from __future__ import annotations
from datetime import date, datetime
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
    PlayerStatus,
    TeamStatus,
    TournamentStatus,
    VenueStatus,
)



def strip_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def strip_required_text(value: object) -> object:
    if value is None:
        raise ValueError("This field cannot be null")
    return strip_text(value)


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    short_name: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=1, max_length=20)
    country: str | None = Field(default=None, max_length=80)
    _strip_text = field_validator(
        "name",
        "short_name",
        "code",
        "country",
        mode="before",
    )(strip_text)


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    short_name: str | None = Field(default=None, min_length=1, max_length=50)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    country: str | None = Field(default=None, max_length=80)

    _strip_required = field_validator(
        "name",
        "short_name",
        "code",
        mode="before",
    )(strip_required_text)

    _strip_optional = field_validator(
        "country",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def require_one_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one team field must be supplied")
        return self


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    short_name: str
    code: str
    country: str | None
    status: TeamStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlayerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=80)
    date_of_birth: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=80)

    _strip_text = field_validator(
        "full_name",
        "short_name",
        "nationality",
        "external_id",
        mode="before",
    )(strip_text)


class PlayerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=80)
    date_of_birth: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=80)

    _strip_required = field_validator(
        "full_name",
        mode="before",
    )(strip_required_text)

    _strip_optional = field_validator(
        "short_name",
        "nationality",
        "external_id",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def require_one_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one player field must be supplied")
        return self


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    short_name: str | None
    date_of_birth: date | None
    nationality: str | None
    external_id: str | None
    status: PlayerStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VenueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    city: str = Field(min_length=1, max_length=100)
    country: str | None = Field(default=None, max_length=80)
    address: str | None = None
    capacity: int | None = Field(default=None, ge=0)

    _strip_text = field_validator(
        "name",
        "city",
        "country",
        "address",
        mode="before",
    )(strip_text)


class VenueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, max_length=80)
    address: str | None = None
    capacity: int | None = Field(default=None, ge=0)

    _strip_required = field_validator(
        "name",
        "city",
        mode="before",
    )(strip_required_text)

    _strip_optional = field_validator(
        "country",
        "address",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def require_one_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one venue field must be supplied")
        return self


class VenueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: str
    country: str | None
    address: str | None
    capacity: int | None
    status: VenueStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


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