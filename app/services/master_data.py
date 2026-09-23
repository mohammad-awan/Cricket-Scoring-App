from __future__ import annotations
from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models import (
    AuditAction,
    Player,
    PlayerStatus,
    Team,
    TeamStatus,
    Tournament,
    TournamentStatus,
    Venue,
    VenueStatus,
)
from app.repositories import (
    PlayerRepository,
    TeamRepository,
    TournamentRepository,
    VenueRepository,
)
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.master_data import (
    PlayerCreate,
    PlayerRead,
    PlayerUpdate,
    TeamCreate,
    TeamRead,
    TeamUpdate,
    TournamentCreate,
    TournamentRead,
    TournamentUpdate,
    VenueCreate,
    VenueRead,
    VenueUpdate,
)
from app.services.common import (
    add_audit_log,
    integrity_conflict,
    service_transaction,
)
from app.utils.text import (
    clean_optional,
    clean_required,
    slugify,
)


def _page(*, items: list[Any], total: int, query: MasterDataQuery) -> dict[str, Any]:
    return {
        "items": items,
        "page": query.page,
        "page_size": query.page_size,
        "total": total,
        "pages": ceil(total / query.page_size)
        if total
        else 0,
    }


def _duplicate_message(resource: str, field: str) -> ConflictError:
    return ConflictError(f"A {resource} with the same {field} already exists.")


async def create_team(session: AsyncSession, payload: TeamCreate) -> Team:
    repository = TeamRepository(session)
    name = clean_required(payload.name)
    short_name = clean_required(payload.short_name)
    code = clean_required(payload.code).upper()
    country = clean_optional(payload.country)

    try:
        async with service_transaction(session):
            duplicate = await repository.find_duplicate(
                name=name,
                code=code,
            )

            if duplicate:
                raise _duplicate_message("team", duplicate)

            team = repository.add(
                Team(
                    name=name,
                    short_name=short_name,
                    code=code,
                    country=country,
                )
            )

            await repository.flush_refresh(team)

            add_audit_log(
                session,
                entity_type="team",
                entity_id=team.id,
                action=AuditAction.CREATED,
                details={
                    "fields": [
                        "name",
                        "short_name",
                        "code",
                        "country",
                    ]
                },
            )

            await session.flush()
            return team

    except IntegrityError as error:
        raise integrity_conflict(error, "Team") from error


async def list_teams(session: AsyncSession, query: MasterDataQuery) -> PageResponse[TeamRead]:
    repository = TeamRepository(session)
    items = await repository.list_page(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        include_archived=query.include_archived,
    )

    total = await repository.count(
        search=query.search,
        include_archived=query.include_archived,
    )

    return PageResponse[TeamRead](
        **_page(
            items=items,
            total=total,
            query=query,
        )
    )


async def get_team(session: AsyncSession, team_id: UUID) -> Team:
    team = await TeamRepository(session).get_by_id(team_id)

    if team is None:
        raise NotFoundError("Team not found")

    return team


async def update_team(session: AsyncSession, team_id: UUID, payload: TeamUpdate) -> Team:
    repository = TeamRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:
        async with service_transaction(session):
            team = await repository.get_by_id(team_id)

            if team is None:
                raise NotFoundError("Team not found")

            if team.status == TeamStatus.ARCHIVED:
                raise ConflictError(
                    "Archived teams cannot be updated"
                )

            name = clean_required(
                data.get("name", team.name)
            )
            code = clean_required(
                data.get("code", team.code)
            ).upper()

            duplicate = await repository.find_duplicate(
                name=name,
                code=code,
                exclude_id=team.id,
            )

            if duplicate:
                raise _duplicate_message("team", duplicate)

            if "name" in data:
                team.name = name

            if "short_name" in data:
                team.short_name = clean_required(
                    data["short_name"]
                )

            if "code" in data:
                team.code = code

            if "country" in data:
                team.country = clean_optional(
                    data["country"]
                )

            team.updated_at = datetime.now(UTC)

            await repository.flush_refresh(team)

            add_audit_log(
                session,
                entity_type="team",
                entity_id=team.id,
                action=AuditAction.UPDATED,
                details={"fields": sorted(data)},
            )

            await session.flush()
            return team

    except IntegrityError as error:
        raise integrity_conflict(error, "Team") from error


async def archive_team(session: AsyncSession, team_id: UUID) -> Team:
    repository = TeamRepository(session)

    try:
        async with service_transaction(session):
            team = await repository.get_by_id(team_id)

            if team is None:
                raise NotFoundError("Team not found")

            if team.status != TeamStatus.ARCHIVED:
                now = datetime.now(UTC)
                team.status = TeamStatus.ARCHIVED
                team.archived_at = now
                team.updated_at = now

                await repository.flush_refresh(team)

                add_audit_log(
                    session,
                    entity_type="team",
                    entity_id=team.id,
                    action=AuditAction.ARCHIVED,
                    details={},
                )

                await session.flush()

            return team

    except IntegrityError as error:
        raise integrity_conflict(error, "Team") from error


async def create_player(session: AsyncSession, payload: PlayerCreate) -> Player:
    repository = PlayerRepository(session)

    full_name = clean_required(payload.full_name)
    short_name = clean_optional(payload.short_name)
    nationality = clean_optional(payload.nationality)
    external_id = clean_optional(payload.external_id)

    try:
        async with service_transaction(session):
            duplicate = await repository.find_duplicate(
                full_name=full_name,
                date_of_birth=payload.date_of_birth,
                external_id=external_id,
            )

            if duplicate:
                raise _duplicate_message(
                    "player",
                    duplicate,
                )

            player = repository.add(
                Player(
                    full_name=full_name,
                    short_name=short_name,
                    date_of_birth=payload.date_of_birth,
                    nationality=nationality,
                    external_id=external_id,
                )
            )

            await repository.flush_refresh(player)

            add_audit_log(
                session,
                entity_type="player",
                entity_id=player.id,
                action=AuditAction.CREATED,
                details={
                    "fields": [
                        "full_name",
                        "date_of_birth",
                        "external_id",
                    ]
                },
            )

            await session.flush()
            return player

    except IntegrityError as error:
        raise integrity_conflict(error, "Player") from error


async def list_players(session: AsyncSession, query: MasterDataQuery) -> PageResponse[PlayerRead]:
    repository = PlayerRepository(session)

    items = await repository.list_page(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        include_archived=query.include_archived,
    )

    total = await repository.count(
        search=query.search,
        include_archived=query.include_archived,
    )

    return PageResponse[PlayerRead](
        **_page(
            items=items,
            total=total,
            query=query,
        )
    )


async def get_player(session: AsyncSession, player_id: UUID) -> Player:
    player = await PlayerRepository(session).get_by_id(player_id)

    if player is None:
        raise NotFoundError("Player not found")

    return player


async def update_player(session: AsyncSession, player_id: UUID, payload: PlayerUpdate) -> Player:
    repository = PlayerRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:
        async with service_transaction(session):
            player = await repository.get_by_id(player_id)

            if player is None:
                raise NotFoundError("Player not found")

            if player.status == PlayerStatus.ARCHIVED:
                raise ConflictError(
                    "Archived players cannot be updated"
                )

            full_name = clean_required(data.get("full_name", player.full_name))
            date_of_birth = data.get("date_of_birth", player.date_of_birth)
            external_id = clean_optional(
                data.get(
                    "external_id",
                    player.external_id,
                )
            )

            duplicate = await repository.find_duplicate(
                full_name=full_name,
                date_of_birth=date_of_birth,
                external_id=external_id,
                exclude_id=player.id,
            )

            if duplicate:
                raise _duplicate_message("player", duplicate)

            if "full_name" in data:
                player.full_name = full_name

            if "short_name" in data:
                player.short_name = clean_optional(data["short_name"])

            if "date_of_birth" in data:
                player.date_of_birth = date_of_birth

            if "nationality" in data:
                player.nationality = clean_optional(data["nationality"])

            if "external_id" in data:
                player.external_id = external_id

            player.updated_at = datetime.now(UTC)

            await repository.flush_refresh(player)

            add_audit_log(
                session,
                entity_type="player",
                entity_id=player.id,
                action=AuditAction.UPDATED,
                details={"fields": sorted(data)},
            )

            await session.flush()
            return player

    except IntegrityError as error:
        raise integrity_conflict(error, "Player") from error


async def archive_player(session: AsyncSession, player_id: UUID) -> Player:
    repository = PlayerRepository(session)

    try:
        async with service_transaction(session):
            player = await repository.get_by_id(player_id)

            if player is None:
                raise NotFoundError("Player not found")

            if player.status != PlayerStatus.ARCHIVED:
                now = datetime.now(UTC)
                player.status = PlayerStatus.ARCHIVED
                player.archived_at = now
                player.updated_at = now

                await repository.flush_refresh(player)

                add_audit_log(
                    session,
                    entity_type="player",
                    entity_id=player.id,
                    action=AuditAction.ARCHIVED,
                    details={},
                )

                await session.flush()

            return player

    except IntegrityError as error:
        raise integrity_conflict(error, "Player") from error


async def create_venue(session: AsyncSession, payload: VenueCreate) -> Venue:
    repository = VenueRepository(session)
    name = clean_required(payload.name)
    city = clean_required(payload.city)

    try:
        async with service_transaction(session):
            if await repository.find_duplicate(
                name=name,
                city=city,
            ):
                raise _duplicate_message(
                    "venue",
                    "name/city",
                )

            venue = repository.add(
                Venue(
                    name=name,
                    city=city,
                    country=clean_optional(payload.country),
                    address=clean_optional(payload.address),
                    capacity=payload.capacity,
                )
            )

            await repository.flush_refresh(venue)

            add_audit_log(
                session,
                entity_type="venue",
                entity_id=venue.id,
                action=AuditAction.CREATED,
                details={
                    "fields": [
                        "name",
                        "city",
                        "country",
                        "capacity",
                    ]
                },
            )

            await session.flush()
            return venue

    except IntegrityError as error:
        raise integrity_conflict(error, "Venue") from error


async def list_venues(session: AsyncSession, query: MasterDataQuery) -> PageResponse[VenueRead]:
    repository = VenueRepository(session)
    items = await repository.list_page(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        include_archived=query.include_archived,
    )

    total = await repository.count(
        search=query.search,
        include_archived=query.include_archived,
    )

    return PageResponse[VenueRead](
        **_page(
            items=items,
            total=total,
            query=query,
        )
    )


async def get_venue(session: AsyncSession, venue_id: UUID) -> Venue:
    venue = await VenueRepository(session).get_by_id(venue_id)

    if venue is None:
        raise NotFoundError("Venue not found")

    return venue


async def update_venue(session: AsyncSession, venue_id: UUID, payload: VenueUpdate) -> Venue:
    repository = VenueRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:
        async with service_transaction(session):
            venue = await repository.get_by_id(venue_id)

            if venue is None:
                raise NotFoundError("Venue not found")

            if venue.status == VenueStatus.ARCHIVED:
                raise ConflictError("Archived venues cannot be updated")

            name = clean_required(data.get("name", venue.name))
            city = clean_required(data.get("city", venue.city))
            if await repository.find_duplicate(
                name=name,
                city=city,
                exclude_id=venue.id,
            ):
                raise _duplicate_message(
                    "venue",
                    "name/city",
                )

            if "name" in data:
                venue.name = name

            if "city" in data:
                venue.city = city

            if "country" in data:
                venue.country = clean_optional(data["country"])

            if "address" in data:
                venue.address = clean_optional(data["address"])

            if "capacity" in data:
                venue.capacity = data["capacity"]

            venue.updated_at = datetime.now(UTC)

            await repository.flush_refresh(venue)

            add_audit_log(
                session,
                entity_type="venue",
                entity_id=venue.id,
                action=AuditAction.UPDATED,
                details={"fields": sorted(data)},
            )

            await session.flush()
            return venue

    except IntegrityError as error:
        raise integrity_conflict(error, "Venue") from error


async def archive_venue(session: AsyncSession, venue_id: UUID) -> Venue:
    repository = VenueRepository(session)

    try:
        async with service_transaction(session):
            venue = await repository.get_by_id(venue_id)

            if venue is None:
                raise NotFoundError("Venue not found")

            if venue.status != VenueStatus.ARCHIVED:
                now = datetime.now(UTC)
                venue.status = VenueStatus.ARCHIVED
                venue.archived_at = now
                venue.updated_at = now

                await repository.flush_refresh(venue)

                add_audit_log(
                    session,
                    entity_type="venue",
                    entity_id=venue.id,
                    action=AuditAction.ARCHIVED,
                    details={},
                )

                await session.flush()

            return venue

    except IntegrityError as error:
        raise integrity_conflict(error, "Venue") from error


def _tournament_slug(
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
    slug = _tournament_slug(
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
                raise _duplicate_message(
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
    repository = TournamentRepository(session)

    items = await repository.list_page(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        include_archived=query.include_archived,
    )

    total = await repository.count(
        search=query.search,
        include_archived=query.include_archived,
    )

    return PageResponse[TournamentRead](
        **_page(
            items=items,
            total=total,
            query=query,
        )
    )


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
                slug = _tournament_slug(
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
                raise _duplicate_message("tournament", duplicate)

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