from __future__ import annotations
from typing import Literal, Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.match_setup import PlayerSummary, TeamSummary


BatterLineupStatus = Literal[
    "batting",
    "dismissed",
    "retired_hurt",
    "retired_out",
    "batted",
    "yet_to_bat",
]


class LiveBattingOrderUpdate(BaseModel):
    """
    New priority for batters who have not yet
    entered the current innings.

    Must list exactly those batters. Batters who
    have already entered keep their slots.
    """

    model_config = ConfigDict(extra="forbid")

    ordered_player_ids: list[UUID] = Field(min_length=2, max_length=20)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_unique_players(self) -> Self:
        if len(set(self.ordered_player_ids)) != len(self.ordered_player_ids):
            raise ValueError("Batting order cannot contain duplicate players.")

        return self


class BattingOrderEntry(BaseModel):
    batting_order: int
    player: PlayerSummary
    status: BatterLineupStatus
    # Entered batters cannot be moved.
    locked: bool


class LiveBattingOrderRead(BaseModel):
    match_id: UUID
    innings_id: UUID
    innings_number: int
    batting_team: TeamSummary
    entries: list[BattingOrderEntry]
    next_automatic_batter_id: UUID | None
