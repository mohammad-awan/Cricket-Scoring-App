from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, BowlingArm, Player, PlayerStatus
from app.repositories.players import PlayerRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.players import PlayerCreate, PlayerRead, PlayerUpdate
from app.services.common import (
    add_audit_log,
    duplicate_conflict,
    integrity_conflict,
    list_master_data,
    service_transaction,
)
from app.utils.text import clean_optional, clean_required


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
                raise duplicate_conflict(
                    "player",
                    duplicate,
                )

            player = repository.add(
                Player(
                    full_name=full_name,
                    short_name=short_name,
                    date_of_birth=(
                        payload.date_of_birth
                    ),
                    nationality=(
                        nationality
                    ),
                    external_id=(
                        external_id
                    ),
                    batting_hand=(
                        payload.batting_hand
                    ),
                    bowling_arm=(
                        payload.bowling_arm
                    ),
                    bowling_style=(
                        payload.bowling_style
                    ),
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
    return await list_master_data(PlayerRepository(session), query, PlayerRead)


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
                raise duplicate_conflict("player", duplicate)

            if "full_name" in data:
                player.full_name = full_name

            if "short_name" in data:
                player.short_name = clean_optional(data["short_name"])

            if "date_of_birth" in data:
                player.date_of_birth = date_of_birth

            if "nationality" in data:
                player.nationality = clean_optional(data["nationality"])

            final_bowling_arm = data.get(
                "bowling_arm",
                player.bowling_arm,
            )
            final_bowling_style = data.get(
                "bowling_style",
                player.bowling_style,
            )

            if (
                final_bowling_arm
                == BowlingArm.NONE
                and
                final_bowling_style
                is not None
            ):
                raise ValidationError(
                    (
                        "bowling_style must be "
                        "empty when bowling_arm "
                        "is none"
                    )
                )

            if (
                final_bowling_style
                is not None
                and
                final_bowling_arm
                is None
            ):
                raise ValidationError(
                    (
                        "bowling_arm is required "
                        "when bowling_style is set"
                    )
                )

            if "external_id" in data:
                player.external_id = (
                    external_id
                )

            if "batting_hand" in data:
                player.batting_hand = (
                    data[
                        "batting_hand"
                    ]
                )

            if "bowling_arm" in data:
                player.bowling_arm = (
                    data[
                        "bowling_arm"
                    ]
                )

            if "bowling_style" in data:
                player.bowling_style = (
                    data[
                        "bowling_style"
                    ]
                )

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
