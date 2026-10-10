from __future__ import annotations
from datetime import datetime
from typing import Literal, Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.enums import DeliveryStatus, RetirementType
from app.schemas.match_setup import PlayerSummary


BatterSelectionMode = Literal["automatic", "manual"]


class RetirementCreate(BaseModel):
    """
    A batter at the crease retires between deliveries.

    The replacement follows the same rules as the
    incoming batter after a wicket: automatic uses the
    live batting order, manual lets the scorer choose
    any eligible batter, including a retired-hurt
    batter resuming their innings.
    """

    model_config = ConfigDict(extra="forbid")

    player_id: UUID
    retirement_type: RetirementType
    selection_mode: BatterSelectionMode = "automatic"
    replacement_player_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.selection_mode == "automatic" and self.replacement_player_id is not None:
            raise ValueError("replacement_player_id must be omitted in automatic selection mode.")

        if self.replacement_player_id == self.player_id:
            raise ValueError("A batter cannot replace themselves.")

        return self


class RetirementUndo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class RetirementRead(BaseModel):
    id: UUID
    event_number: int
    after_delivery_number: int
    player: PlayerSummary
    retirement_type: RetirementType
    replacement_player: PlayerSummary | None
    selection_mode: BatterSelectionMode
    reason: str
    status: DeliveryStatus
    created_at: datetime
