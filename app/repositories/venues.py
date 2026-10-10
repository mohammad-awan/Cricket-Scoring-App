from __future__ import annotations
from uuid import UUID
from sqlalchemy import func
from app.models import Venue
from app.repositories.base_master_data import MasterDataRepository


class VenueRepository(MasterDataRepository[Venue]):
    model = Venue
    search_fields = (Venue.name, Venue.city, Venue.country)

    async def find_duplicate(
        self,
        *,
        name: str,
        city: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        return await self.exists(
            func.lower(Venue.name) == name.lower(),
            func.lower(Venue.city) == city.lower(),
            exclude_id=exclude_id,
        )
