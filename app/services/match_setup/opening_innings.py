from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, Innings, InningsStatus, MatchStatus
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import MatchSetupRead, OpeningInningsSetup
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.match_setup.presenters import match_setup_read, reload_match
from app.services.match_setup.rules import (
    playing_team_ids,
    evaluate_readiness,
    derive_first_innings_teams,
)


async def setup_opening_innings(
    session: AsyncSession,
    match_id: UUID,
    payload: OpeningInningsSetup,
) -> MatchSetupRead:

    repository = (
        MatchSetupRepository(
            session
        )
    )

    try:

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
                    "Opening innings can "
                    "only be configured "
                    "while the match is draft"
                )

            readiness = evaluate_readiness(
                match
            )

            if (
                not readiness
                .toss_complete
            ):
                raise ValidationError(
                    "Complete the toss "
                    "before innings setup"
                )

            if (
                not readiness
                .team_a_players_complete
                or not readiness
                .team_b_players_complete
            ):
                raise ValidationError(
                    "Both playing teams "
                    "must contain exactly "
                    f"{match.players_per_side} "
                    "players"
                )

            (
                batting_team_id,
                bowling_team_id,
            ) = derive_first_innings_teams(
                match
            )

            batting_xi = (
                playing_team_ids(
                    match,
                    batting_team_id,
                )
            )

            bowling_xi = (
                playing_team_ids(
                    match,
                    bowling_team_id,
                )
            )

            if (
                payload.striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Striker must belong "
                    "to the batting team's "
                    "playing team"
                )

            if (
                payload.non_striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Non-striker must belong "
                    "to the batting team's "
                    "playing team"
                )

            if (
                payload.opening_bowler_id
                not in bowling_xi
            ):
                raise ValidationError(
                    "Opening bowler must "
                    "belong to the bowling "
                    "team's playing team"
                )

            first_innings = (
                await repository
                .get_first_innings(
                    match.id
                )
            )

            if first_innings is None:

                first_innings = Innings(
                    match_id=(
                        match.id
                    ),

                    innings_number=1,

                    batting_team_id=(
                        batting_team_id
                    ),

                    bowling_team_id=(
                        bowling_team_id
                    ),

                    status=(
                        InningsStatus.PENDING
                    ),

                    striker_id=(
                        payload.striker_id
                    ),

                    non_striker_id=(
                        payload
                        .non_striker_id
                    ),

                    current_bowler_id=(
                        payload
                        .opening_bowler_id
                    ),
                )

                session.add(
                    first_innings
                )

                audit_action = (
                    AuditAction.CREATED
                )

            else:

                if first_innings.deliveries:
                    raise ConflictError(
                        "Opening participants "
                        "cannot be changed "
                        "after scoring starts"
                    )

                first_innings.batting_team_id = (
                    batting_team_id
                )

                first_innings.bowling_team_id = (
                    bowling_team_id
                )

                first_innings.status = (
                    InningsStatus.PENDING
                )

                first_innings.striker_id = (
                    payload.striker_id
                )

                first_innings.non_striker_id = (
                    payload
                    .non_striker_id
                )

                first_innings.current_bowler_id = (
                    payload
                    .opening_bowler_id
                )

                first_innings.updated_at = (
                    datetime.now(
                        UTC
                    )
                )

                audit_action = (
                    AuditAction.UPDATED
                )

            await session.flush()

            match.updated_at = (
                datetime.now(
                    UTC
                )
            )

            add_audit_log(
                session,

                entity_type=(
                    "innings"
                ),

                entity_id=(
                    first_innings.id
                ),

                action=(
                    audit_action
                ),

                details={
                    "match_id":
                        str(
                            match.id
                        ),

                    "innings_number":
                        1,

                    "batting_team_id":
                        str(
                            batting_team_id
                        ),

                    "bowling_team_id":
                        str(
                            bowling_team_id
                        ),

                    "striker_id":
                        str(
                            payload
                            .striker_id
                        ),

                    "non_striker_id":
                        str(
                            payload
                            .non_striker_id
                        ),

                    "opening_bowler_id":
                        str(
                            payload
                            .opening_bowler_id
                        ),
                },
            )

            await session.flush()

        loaded = await reload_match(
            session,
            repository,
            match_id,
        )

        return match_setup_read(loaded)

    except IntegrityError as error:
        raise integrity_conflict(error, "Opening innings") from error
