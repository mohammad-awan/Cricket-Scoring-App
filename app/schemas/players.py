from __future__ import annotations
from datetime import date, datetime
from typing import Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import BattingHand, BowlingArm, BowlingStyle, PlayerStatus
from app.schemas.common import strip_required_text, strip_text


class PlayerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=80)
    date_of_birth:  date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=80)
    batting_hand: BattingHand | None = None
    bowling_arm: BowlingArm | None = None
    bowling_style: BowlingStyle | None = None

    _strip_text = field_validator(
        "full_name",
        "short_name",
        "nationality",
        "external_id",
        mode="before",
    )(
        strip_text
    )


    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_not_future(cls, value: date | None) -> date | None:
        if (
            value is not None
            and
            value > date.today()
        ):
            raise ValueError(
                (
                    "date_of_birth "
                    "cannot be in the future"
                )
            )

        return value


    @model_validator(mode="after")
    def validate_bowling_profile(self) -> Self:
        if (
            self.bowling_arm
            == BowlingArm.NONE
            and
            self.bowling_style
            is not None
        ):
            raise ValueError(
                (
                    "bowling_style must "
                    "be empty when "
                    "bowling_arm is none"
                )
            )

        if (
            self.bowling_style
            is not None
            and
            self.bowling_arm
            is None
        ):

            raise ValueError(
                (
                    "bowling_arm is "
                    "required when "
                    "bowling_style is set"
                )
            )

        return self


class PlayerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=80)
    date_of_birth: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=80)
    batting_hand: BattingHand | None = None
    bowling_arm: BowlingArm | None = None
    bowling_style: BowlingStyle | None = None


    _strip_required = (
        field_validator(
            "full_name",
            mode="before",
        )(
            strip_required_text
        )
    )


    _strip_optional = (
        field_validator(
            "short_name",
            "nationality",
            "external_id",
            mode="before",
        )(
            strip_text
        )
    )


    @field_validator(
        "date_of_birth"
    )
    @classmethod
    def date_of_birth_not_future(
        cls,
        value: date | None,
    ) -> date | None:

        if (
            value is not None
            and
            value > date.today()
        ):

            raise ValueError(
                (
                    "date_of_birth "
                    "cannot be in the future"
                )
            )

        return value


    @model_validator(mode="after")
    def require_one_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(
                (
                    "At least one player "
                    "field must be supplied"
                )
            )

        if (
            (
                "bowling_arm"
                in self.model_fields_set
            )

            and
            self.bowling_arm
            == BowlingArm.NONE
            and
            self.bowling_style
            is not None
        ):

            raise ValueError(
                (
                    "bowling_style must "
                    "be empty when "
                    "bowling_arm is none"
                )
            )

        return self


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    short_name: str | None
    date_of_birth: date | None
    nationality: str | None
    external_id: str | None
    batting_hand: BattingHand | None
    bowling_arm: BowlingArm | None
    bowling_style: BowlingStyle | None
    status: PlayerStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
