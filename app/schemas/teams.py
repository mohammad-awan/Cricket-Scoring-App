from __future__ import annotations
from datetime import datetime
from typing import Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import TeamStatus
from app.schemas.common import strip_required_text, strip_text


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
