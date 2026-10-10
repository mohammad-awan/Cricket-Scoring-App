from __future__ import annotations
from datetime import date
from uuid import UUID
from sqlalchemy import func
from app.models import Player
from app.repositories.base_master_data import MasterDataRepository


class PlayerRepository(MasterDataRepository[Player]):
    model = Player
    search_fields = (
        Player.full_name,
        Player.short_name,
        Player.nationality,
        Player.external_id,
    )

    async def find_duplicate(
        self,
        *,
        full_name: str,
        date_of_birth: date | None,
        external_id: str | None,
        exclude_id: UUID | None = None,
    ) -> str | None:
        if external_id and await self.exists(
            Player.external_id == external_id,
            exclude_id=exclude_id,
        ):
            return "external_id"

        name_condition = (func.lower(Player.full_name) == full_name.lower())

        if date_of_birth is not None:
            name_condition = (
                name_condition
                & (Player.date_of_birth == date_of_birth)
            )

        if await self.exists(
            name_condition,
            exclude_id=exclude_id,
        ):
            return "full_name/date_of_birth"

        return None
