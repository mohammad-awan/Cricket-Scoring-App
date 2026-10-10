from __future__ import annotations
from typing import Any, Generic, TypeVar
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base


ModelT = TypeVar("ModelT", bound=Base)


class MasterDataRepository(Generic[ModelT]):
    model: type[ModelT]
    archive_status: str = "archived"
    search_fields: tuple[Any, ...] = ()

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def build_conditions(self, *, search: str | None = None, include_archived: bool = False) -> list[Any]:
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

    async def exists(self, *conditions: Any, exclude_id: UUID | None) -> bool:
        statement = select(self.model.id).where(*conditions)  # type: ignore[attr-defined]

        if exclude_id is not None:
            statement = statement.where(self.model.id != exclude_id)  # type: ignore[attr-defined]

        return (
            await self.session.scalar(statement.limit(1))
            is not None
        )

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        statement = select(self.model).where(
            self.model.id == entity_id
        )
        return await self.session.scalar(statement)

    async def list_page(self, *, page: int, page_size: int, search: str | None = None, include_archived: bool = False) -> list[ModelT]:
        statement = (
            select(self.model)
            .where(
                *self.build_conditions(
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
            *self.build_conditions(
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
