"""Stage 11 tournament series: groups the editions of one competition.

Each Tournament row is one edition; a series (e.g. "National T20 Cup")
links them via tournaments.series_id and edition_number. Validation is
intentionally light: a name is required and slugs stay unique.
"""

from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Tournament, TournamentSeries
from app.repositories.tournaments import TournamentRepository, TournamentSeriesRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.tournaments import (
    TournamentSeriesCreate,
    TournamentSeriesRead,
    TournamentSeriesUpdate,
)
from app.services.common import list_master_data
from app.services.tournaments import tournament_transaction
from app.utils.text import clean_optional, slugify


def _series_slug(value: str) -> str:
    try:
        return slugify(value)
    except ValueError as error:
        raise ValidationError("The series slug must contain letters or numbers") from error


async def create_tournament_series(
    session: AsyncSession,
    payload: TournamentSeriesCreate,
) -> TournamentSeries:
    repository = TournamentSeriesRepository(session)
    slug = _series_slug(payload.slug or payload.name)

    async with tournament_transaction(session, "Tournament series"):
        if await repository.exists(TournamentSeries.slug == slug, exclude_id=None):
            raise ConflictError("A tournament series with this slug already exists")

        if await repository.exists(
            func.lower(TournamentSeries.name) == payload.name.lower(),
            exclude_id=None,
        ):
            raise ConflictError("A tournament series with this name already exists")

        series = repository.add(
            TournamentSeries(
                name=payload.name,
                slug=slug,
                organizer=clean_optional(payload.organizer),
                description=payload.description,
            )
        )
        return await repository.flush_refresh(series)


async def list_tournament_series(
    session: AsyncSession,
    query: MasterDataQuery,
) -> PageResponse[TournamentSeriesRead]:
    return await list_master_data(TournamentSeriesRepository(session), query, TournamentSeriesRead)


async def get_tournament_series(session: AsyncSession, series_id: UUID) -> TournamentSeries:
    series = await TournamentSeriesRepository(session).get_by_id(series_id)
    if series is None:
        raise NotFoundError("Tournament series not found")

    return series


async def update_tournament_series(
    session: AsyncSession,
    series_id: UUID,
    payload: TournamentSeriesUpdate,
) -> TournamentSeries:
    repository = TournamentSeriesRepository(session)
    data = payload.model_dump(exclude_unset=True)

    async with tournament_transaction(session, "Tournament series"):
        series = await repository.get_by_id(series_id)
        if series is None:
            raise NotFoundError("Tournament series not found")

        if data.get("name"):
            if await repository.exists(
                func.lower(TournamentSeries.name) == data["name"].lower(),
                exclude_id=series_id,
            ):
                raise ConflictError("A tournament series with this name already exists")
            series.name = data["name"]

        if "organizer" in data:
            series.organizer = clean_optional(data["organizer"])

        if "description" in data:
            series.description = data["description"]

        series.updated_at = datetime.now(UTC)
        return await repository.flush_refresh(series)


async def list_series_editions(
    session: AsyncSession,
    series_id: UUID,
) -> list[Tournament]:
    await get_tournament_series(session, series_id)
    return await TournamentRepository(session).list_editions(series_id)
