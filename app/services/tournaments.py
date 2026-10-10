from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, Tournament, TournamentStatus
from app.repositories.tournaments import TournamentRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.tournaments import TournamentCreate, TournamentRead, TournamentUpdate
from app.services.common import (
    add_audit_log,
    duplicate_conflict,
    integrity_conflict,
    list_master_data,
    service_transaction,
)
from app.utils.text import clean_optional, clean_required, slugify


def tournament_slug(
    name: str,
    season: str | None,
    supplied_slug: str | None,
) -> str:
    try:
        if supplied_slug:
            return slugify(supplied_slug)

        value = f"{name}-{season}" if season else name
        return slugify(value)

    except ValueError as error:
        raise ValidationError(
            "The tournament slug must contain letters or numbers"
        ) from error


async def create_tournament(session: AsyncSession, payload: TournamentCreate) -> Tournament:
    repository = TournamentRepository(session)
    name = clean_required(payload.name)
    season = clean_optional(payload.season)
    slug = tournament_slug(
        name,
        season,
        clean_optional(payload.slug),
    )

    try:
        async with service_transaction(session):
            duplicate = await repository.find_duplicate(
                name=name,
                season=season,
                slug=slug,
            )

            if duplicate:
                raise duplicate_conflict(
                    "tournament",
                    duplicate,
                )

            tournament = repository.add(
                Tournament(
                    name=name,
                    slug=slug,
                    season=season,
                    organizer=clean_optional(
                        payload.organizer
                    ),
                    description=clean_optional(
                        payload.description
                    ),
                    start_date=payload.start_date,
                    end_date=payload.end_date,
                )
            )

            await repository.flush_refresh(tournament)

            add_audit_log(
                session,
                entity_type="tournament",
                entity_id=tournament.id,
                action=AuditAction.CREATED,
                details={
                    "fields": [
                        "name",
                        "slug",
                        "season",
                        "start_date",
                        "end_date",
                    ]
                },
            )

            await session.flush()
            return tournament

    except IntegrityError as error:
        raise integrity_conflict(
            error,
            "Tournament",
        ) from error


async def list_tournaments(session: AsyncSession, query: MasterDataQuery) -> PageResponse[TournamentRead]:
    return await list_master_data(TournamentRepository(session), query, TournamentRead)


async def get_tournament(session: AsyncSession, tournament_id: UUID) -> Tournament:
    tournament = await TournamentRepository(session).get_by_id(tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    return tournament


async def update_tournament(session: AsyncSession, tournament_id: UUID, payload: TournamentUpdate) -> Tournament:
    repository = TournamentRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:
        async with service_transaction(session):
            tournament = await repository.get_by_id(tournament_id)
            if tournament is None:
                raise NotFoundError("Tournament not found")

            if tournament.status == TournamentStatus.ARCHIVED:
                raise ConflictError("Archived tournaments cannot be updated")

            name = clean_required(data.get("name", tournament.name))
            season = clean_optional(data.get("season", tournament.season))
            slug = tournament.slug

            if "slug" in data:
                slug = tournament_slug(
                    name,
                    season,
                    clean_optional(data["slug"]),
                )

            start_date = data.get("start_date", tournament.start_date)
            end_date = data.get("end_date", tournament.end_date)

            if (
                start_date
                and end_date
                and end_date < start_date
            ):
                raise ValidationError(
                    "end_date must be on or after start_date"
                )

            duplicate = await repository.find_duplicate(
                name=name,
                season=season,
                slug=slug,
                exclude_id=tournament.id,
            )

            if duplicate:
                raise duplicate_conflict("tournament", duplicate)

            if "name" in data:
                tournament.name = name

            if "slug" in data:
                tournament.slug = slug

            if "season" in data:
                tournament.season = season

            if "organizer" in data:
                tournament.organizer = clean_optional(data["organizer"])

            if "description" in data:
                tournament.description = clean_optional(data["description"])

            if "start_date" in data:
                tournament.start_date = start_date

            if "end_date" in data:
                tournament.end_date = end_date

            tournament.updated_at = datetime.now(UTC)

            await repository.flush_refresh(tournament)

            add_audit_log(
                session,
                entity_type="tournament",
                entity_id=tournament.id,
                action=AuditAction.UPDATED,
                details={"fields": sorted(data)},
            )

            await session.flush()
            return tournament

    except IntegrityError as error:
        raise integrity_conflict(
            error,
            "Tournament",
        ) from error


async def archive_tournament(session: AsyncSession, tournament_id: UUID) -> Tournament:
    repository = TournamentRepository(session)

    try:
        async with service_transaction(session):
            tournament = await repository.get_by_id(
                tournament_id
            )

            if tournament is None:
                raise NotFoundError("Tournament not found")

            if tournament.status != TournamentStatus.ARCHIVED:
                now = datetime.now(UTC)
                tournament.status = TournamentStatus.ARCHIVED
                tournament.archived_at = now
                tournament.updated_at = now

                await repository.flush_refresh(tournament)

                add_audit_log(
                    session,
                    entity_type="tournament",
                    entity_id=tournament.id,
                    action=AuditAction.ARCHIVED,
                    details={},
                )

                await session.flush()

            return tournament

    except IntegrityError as error:
        raise integrity_conflict(
            error,
            "Tournament",
        ) from error
