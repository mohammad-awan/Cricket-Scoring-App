from __future__ import annotations
from datetime import datetime
from typing import Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import VenueStatus
from app.schemas.common import strip_required_text, strip_text


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
