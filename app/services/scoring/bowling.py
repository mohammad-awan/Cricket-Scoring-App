from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import BowlerChange, ScoringStateRead
from app.services.common import add_audit_log, service_transaction
from app.services.scoring.calculations import overs_complete, previous_over_bowler_id
from app.services.scoring.state import current_state, ensure_scoreable, rebuild_innings_state
from app.domain.bowling import validate_bowler_quota


async def change_bowler(
    session: AsyncSession,
    match_id: UUID,
    payload: BowlerChange,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    async with service_transaction(
        session
    ):

        innings = (
            await repository
            .lock_current_innings(
                match_id
            )
        )

        if innings is None:

            raise NotFoundError(
                "First innings has "
                "not been configured"
            )

        match = (
            await repository
            .get_match(
                match_id
            )
        )

        if match is None:

            raise NotFoundError(
                "Match not found"
            )

        ensure_scoreable(
            match,
            innings,
        )

        deliveries = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        derived = (
            rebuild_innings_state(
                innings,
                deliveries,
                await repository.get_official_retirements(innings.id),
                balls_per_over=(
                    match
                    .balls_per_over
                ),
            )
        )

        if (
            derived.legal_balls
            == 0
        ):

            raise ConflictError(
                "The opening bowler "
                "is already configured "
                "for this innings"
            )

        if (
            derived.legal_balls
            % match.balls_per_over
            != 0
        ):

            raise ConflictError(
                "Bowler can only "
                "be changed at an "
                "over boundary"
            )

        if overs_complete(
            match,
            derived.legal_balls,
        ):

            raise ConflictError(
                "The configured "
                "over limit has "
                "been reached"
            )

        if (
            payload.bowler_id
            == previous_over_bowler_id(
                deliveries
            )
        ):

            raise ValidationError(
                "This bowler bowled "
                "the previous over. "
                "Choose a different "
                "bowler"
            )

        belongs = (
            await repository
            .is_playing_team_player(
                match_id=(
                    match.id
                ),

                team_id=(
                    innings
                    .bowling_team_id
                ),

                player_id=(
                    payload
                    .bowler_id
                ),
            )
        )

        if not belongs:

            raise ValidationError(
                "Bowler must belong "
                "to the bowling "
                "team's selected "
                "playing team"
            )

        player = (
            await repository
            .get_player(
                payload.bowler_id
            )
        )

        if player is None:

            raise NotFoundError(
                "Bowler not found"
            )

        if payload.bowler_id in {
            derived.striker_id,
            derived.non_striker_id,
        }:
            raise ValidationError(
                "A current batter cannot be selected "
                "as the bowler."
            )

        validate_bowler_quota(
            match=match,
            deliveries=deliveries,
            bowler_id=payload.bowler_id,
            starting_new_over=True,
        )

        innings.current_bowler_id = (
            payload.bowler_id
        )

        add_audit_log(
            session,

            entity_type=(
                "innings"
            ),

            entity_id=(
                innings.id
            ),

            action=(
                AuditAction.UPDATED
            ),

            details={
                "setup":
                    "current_bowler",

                "bowler_id":
                    str(
                        payload
                        .bowler_id
                    ),

                "after_legal_balls":
                    derived
                    .legal_balls,
            },
        )

        await session.flush()

    return await current_state(
        repository,
        match_id,
        "bowler change",
    )
