from __future__ import annotations
from uuid import UUID
from sqlalchemy import func
from app.models import Tournament
from app.repositories.base_master_data import MasterDataRepository


class TournamentRepository(MasterDataRepository[Tournament]):
    model = Tournament
    search_fields = (
        Tournament.name,
        Tournament.slug,
        Tournament.season,
        Tournament.organizer,
    )

    async def find_duplicate(
        self,
        *,
        name: str,
        season: str | None,
        slug: str,
        exclude_id: UUID | None = None,
    ) -> str | None:
        if await self.exists(
            Tournament.slug == slug,
            exclude_id=exclude_id,
        ):
            return "slug"

        season_condition = (
            Tournament.season.is_(None)
            if season is None
            else Tournament.season == season
        )

        if await self.exists(
            func.lower(Tournament.name) == name.lower(),
            season_condition,
            exclude_id=exclude_id,
        ):
            return "name/season"

        return None
