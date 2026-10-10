from __future__ import annotations
from uuid import UUID
from sqlalchemy import func
from app.models import Team
from app.repositories.base_master_data import MasterDataRepository


class TeamRepository(MasterDataRepository[Team]):
    model = Team
    search_fields = (
        Team.name,
        Team.short_name,
        Team.code,
        Team.country,
    )

    async def find_duplicate(self, *, name: str, code: str, exclude_id: UUID | None = None) -> str | None:
        if await self.exists(
            Team.code == code,
            exclude_id=exclude_id,
        ):
            return "code"

        if await self.exists(
            func.lower(Team.name) == name.lower(),
            exclude_id=exclude_id,
        ):
            return "name"

        return None
