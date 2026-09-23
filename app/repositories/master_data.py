from __future__ import annotations
from datetime import date
from typing import Any, Generic, TypeVar
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base
from app.models import Player, Team, Tournament, Venue


ModelT = TypeVar("ModelT", bound=Base)


class MasterDataRepository(Generic[ModelT]):
    model: type[ModelT]
    archive_status: str = "archived"
    search_fields: tuple[Any, ...] = ()

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _conditions(self, *, search: str | None = None, include_archived: bool = False) -> list[Any]:
        conditions: list[Any] = []

        if not include_archived:
            conditions.append(
                self.model.status != self.archive_status  # type: ignore[attr-defined]
            )

        if search:
            pattern = f"%{search.strip().lower()}%"
            conditions.append(
                or_(
                    *(
                        func.lower(field).like(pattern)
                        for field in self.search_fields
                    )
                )
            )

        return conditions

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        statement = select(self.model).where(
            self.model.id == entity_id
        )
        return await self.session.scalar(statement)

    async def list_page(self, *, page: int, page_size: int, search: str | None = None, include_archived: bool = False) -> list[ModelT]:
        statement = (
            select(self.model)
            .where(
                *self._conditions(
                    search=search,
                    include_archived=include_archived,
                )
            )
            .order_by(
                self.model.created_at.desc(),  # type: ignore[attr-defined]
                self.model.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def count(self, *, search: str | None = None, include_archived: bool = False) -> int:
        statement = select(
            func.count(self.model.id)  # type: ignore[attr-defined]
        ).where(
            *self._conditions(
                search=search,
                include_archived=include_archived,
            )
        )

        return int(await self.session.scalar(statement) or 0)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def flush_refresh(self, entity: ModelT) -> ModelT:
        await self.session.flush()
        await self.session.refresh(entity)
        return entity


class TeamRepository(MasterDataRepository[Team]):
    model = Team
    search_fields = (
        Team.name,
        Team.short_name,
        Team.code,
        Team.country,
    )

    async def find_duplicate(self, *, name: str, code: str, exclude_id: UUID | None = None) -> str | None:
        if await self._exists(
            Team.code == code,
            exclude_id=exclude_id,
        ):
            return "code"

        if await self._exists(
            func.lower(Team.name) == name.lower(),
            exclude_id=exclude_id,
        ):
            return "name"

        return None

    async def _exists(self, condition: Any, *, exclude_id: UUID | None) -> bool:
        statement = select(Team.id).where(condition)

        if exclude_id is not None:
            statement = statement.where(Team.id != exclude_id)

        return (
            await self.session.scalar(statement.limit(1))
            is not None
        )


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
        if external_id and await self._exists(
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

        if await self._exists(
            name_condition,
            exclude_id=exclude_id,
        ):
            return "full_name/date_of_birth"

        return None

    async def _exists(self, condition: Any, *, exclude_id: UUID | None) -> bool:
        statement = select(Player.id).where(condition)

        if exclude_id is not None:
            statement = statement.where(Player.id != exclude_id)

        return (
            await self.session.scalar(statement.limit(1))
            is not None
        )


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
        statement = select(Venue.id).where(
            func.lower(Venue.name) == name.lower(),
            func.lower(Venue.city) == city.lower(),
        )

        if exclude_id is not None:
            statement = statement.where(Venue.id != exclude_id)

        return (
            await self.session.scalar(statement.limit(1))
            is not None
        )


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
        slug_statement = select(Tournament.id).where(
            Tournament.slug == slug
        )

        if exclude_id is not None:
            slug_statement = slug_statement.where(
                Tournament.id != exclude_id
            )

        if await self.session.scalar(
            slug_statement.limit(1)
        ) is not None:
            return "slug"

        season_condition = (
            Tournament.season.is_(None)
            if season is None
            else Tournament.season == season
        )

        name_statement = select(Tournament.id).where(
            func.lower(Tournament.name) == name.lower(),
            season_condition,
        )

        if exclude_id is not None:
            name_statement = name_statement.where(Tournament.id != exclude_id)

        if await self.session.scalar(name_statement.limit(1)) is not None:
            return "name/season"

        return None