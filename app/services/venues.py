from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models import AuditAction, Venue, VenueStatus
from app.repositories.venues import VenueRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.venues import VenueCreate, VenueRead, VenueUpdate
from app.services.common import (
    add_audit_log,
    duplicate_conflict,
    integrity_conflict,
    list_master_data,
    service_transaction,
)
from app.utils.text import clean_optional, clean_required


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
                raise duplicate_conflict(
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
    return await list_master_data(VenueRepository(session), query, VenueRead)


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
                raise duplicate_conflict(
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
