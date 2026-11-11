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
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )
    image_url: str | None = Field(default=None, max_length=2048)

    _strip_text = field_validator(
        "name",
        "city",
        "country",
        "address",
        mode="before",
    )(strip_text)

    @model_validator(mode="after")
    def validate_coordinates(self) -> Self:
        latitude_set = "latitude" in self.model_fields_set
        longitude_set = "longitude" in self.model_fields_set

        if latitude_set != longitude_set:
            raise ValueError("Latitude and longitude must be supplied together")

        if latitude_set and (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must both be set or both be null")

        return self


class VenueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, max_length=80)
    address: str | None = None
    capacity: int | None = Field(default=None, ge=0)
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )
    image_url: str | None = Field(default=None, max_length=2048)

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

    @model_validator(mode="after")
    def validate_coordinates(self) -> Self:
        latitude_set = "latitude" in self.model_fields_set
        longitude_set = "longitude" in self.model_fields_set

        if latitude_set != longitude_set:
            raise ValueError("Latitude and longitude must be supplied together")

        if latitude_set and (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must both be set or both be null")

        return self


class VenueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: str
    country: str | None
    address: str | None
    capacity: int | None
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None
    status: VenueStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
