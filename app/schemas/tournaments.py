from __future__ import annotations
from datetime import date, datetime
from typing import Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import TournamentStatus
from app.schemas.common import strip_required_text, strip_text


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
