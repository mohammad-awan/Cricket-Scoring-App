from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    AuditAction,
    PlayerStatus,
    TeamPlayer,
    TeamStatus,
)
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import (
    PlayerSummary,
    SquadMemberCreate,
    TeamSquadMembershipRead,
)
from app.services.common import (
    add_audit_log,
    integrity_conflict,
    service_transaction,
)



async def list_team_squad(session: AsyncSession, team_id: UUID) -> list[TeamSquadMembershipRead]:

    repository = MatchSetupRepository(session)
    team = await repository.get_team(team_id)

    if team is None:
        raise NotFoundError("Team not found")

    squad = await repository.get_active_squad(team_id)

    return [
        TeamSquadMembershipRead(
            id=item.id,
            team_id=item.team_id,
            player=PlayerSummary.model_validate(item.player),
            role=item.role,
            squad_number=item.squad_number,
            is_active=item.is_active,
        )
        for item in squad
    ]


async def add_player_to_team_squad(
    session: AsyncSession,
    team_id: UUID,
    payload: SquadMemberCreate,
) -> TeamSquadMembershipRead:

    repository = MatchSetupRepository(session)
    try:
        async with service_transaction(session):
            team = await repository.get_team(team_id)
            if team is None:
                raise NotFoundError("Team not found")

            if (
                team.status
                != TeamStatus.ACTIVE
                or team.archived_at
                is not None
            ):
                raise ConflictError(
                    "Only active teams "
                    "can receive squad players"
                )

            player = await repository.get_player(payload.player_id)

            if player is None:
                raise NotFoundError("Player not found")

            if (
                player.status
                != PlayerStatus.ACTIVE
                or player.archived_at
                is not None
            ):
                raise ConflictError(
                    "Only active players "
                    "can be added to a squad"
                )

            membership = (
                await repository
                .get_team_player_membership(
                    team_id,
                    payload.player_id,
                )
            )
            created_new = membership is None
            if membership is None:
                membership = TeamPlayer(
                    team_id=team_id,
                    player_id=payload.player_id,
                    role=payload.role,
                    squad_number=payload.squad_number,
                    is_active=True,
                )
                session.add(membership)

            else:

                membership.role = payload.role
                membership.squad_number = payload.squad_number
                membership.is_active = True
                membership.left_on = None
                membership.updated_at = datetime.now(UTC)

            await session.flush()
            membership = (
                await repository
                .get_team_player_membership(
                    team_id,
                    payload.player_id,
                )
            )

            if membership is None:
                raise NotFoundError(
                    "Team squad membership "
                    "not found after save"
                )

            add_audit_log(
                session,
                entity_type="team_player",
                entity_id=membership.id,
                action=(
                    AuditAction.CREATED
                    if created_new
                    else AuditAction.UPDATED
                ),
                details={
                    "team_id": str(team_id),
                    "player_id": str(payload.player_id),
                    "is_active": True,
                },
            )
            await session.flush()
            return TeamSquadMembershipRead(
                id=membership.id,
                team_id=membership.team_id,
                player=PlayerSummary.model_validate(membership.player),
                role=membership.role,
                squad_number=membership.squad_number,
                is_active=membership.is_active,
            )

    except IntegrityError as error:
        raise integrity_conflict(error, "Team squad membership") from error


async def deactivate_team_squad_member(
    session: AsyncSession,
    team_id: UUID,
    player_id: UUID,
) -> TeamSquadMembershipRead:

    repository = MatchSetupRepository(session)
    async with service_transaction(session):
        membership = (
            await repository
            .get_team_player_membership(
                team_id,
                player_id,
            )
        )
        if membership is None:
            raise NotFoundError(
                "Team squad membership "
                "not found"
            )

        membership.is_active = False
        membership.left_on = datetime.now(UTC).date()
        membership.updated_at = datetime.now(UTC)
        await session.flush()
        add_audit_log(
            session,
            entity_type="team_player",
            entity_id=membership.id,
            action=AuditAction.UPDATED,
            details={
                "team_id": str(team_id),
                "player_id": str(player_id),
                "is_active": False,
            },
        )

        await session.flush()

        return TeamSquadMembershipRead(
            id=membership.id,
            team_id=membership.team_id,
            player=(
                PlayerSummary.model_validate(membership.player)),
            role=membership.role,
            squad_number=membership.squad_number,
            is_active=membership.is_active,
        )