from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models import AuditAction, Team, TeamStatus
from app.repositories.teams import TeamRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.teams import TeamCreate, TeamRead, TeamUpdate
from app.services.common import (
    add_audit_log,
    duplicate_conflict,
    integrity_conflict,
    list_master_data,
    service_transaction,
)
from app.utils.text import clean_optional, clean_required


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
                raise duplicate_conflict("team", duplicate)

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
    return await list_master_data(TeamRepository(session), query, TeamRead)


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
                raise duplicate_conflict("team", duplicate)

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
