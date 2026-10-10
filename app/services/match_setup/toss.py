from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, MatchStatus
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import MatchSetupRead, TossSetup
from app.services.common import add_audit_log, service_transaction
from app.services.match_setup.presenters import match_setup_read, reload_match


async def set_toss(
    session: AsyncSession,
    match_id: UUID,
    payload: TossSetup,
) -> MatchSetupRead:

    repository = (
        MatchSetupRepository(
            session
        )
    )

    async with service_transaction(
        session
    ):

        match = (
            await repository
            .get_match(
                match_id,
                for_update=True,
            )
        )

        if match is None:
            raise NotFoundError(
                "Match not found"
            )

        if (
            match.status
            != MatchStatus.DRAFT
        ):
            raise ConflictError(
                "Toss can only be changed "
                "while the match is draft"
            )

        if (
            payload.winner_team_id
            not in {
                match.team_a_id,
                match.team_b_id,
            }
        ):
            raise ValidationError(
                "Toss winner must be "
                "Team A or Team B"
            )

        if match.innings:
            raise ConflictError(
                "Toss cannot be changed "
                "after opening innings setup "
                "has been created"
            )

        match.toss_winner_id = (
            payload.winner_team_id
        )

        match.toss_decision = (
            payload.decision
        )

        match.updated_at = (
            datetime.now(
                UTC
            )
        )

        await session.flush()

        add_audit_log(
            session,

            entity_type=(
                "match"
            ),

            entity_id=(
                match.id
            ),

            action=(
                AuditAction.UPDATED
            ),

            details={
                "setup":
                    "toss",

                "winner_team_id":
                    str(
                        payload
                        .winner_team_id
                    ),

                "decision":
                    payload
                    .decision
                    .value,
            },
        )

        await session.flush()

    loaded = await reload_match(
        session,
        repository,
        match_id,
    )

    return match_setup_read(
        loaded
    )
