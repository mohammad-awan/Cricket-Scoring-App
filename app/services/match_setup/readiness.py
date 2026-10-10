from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, MatchStatus
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import MatchSetupRead
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.match_setup.presenters import match_setup_read, reload_match
from app.services.match_setup.rules import (
    playing_team_ids,
    evaluate_readiness,
    derive_first_innings_teams,
)
from app.services.match_setup.validators import validate_match_references
from app.domain.batting_order import validate_batting_order


async def mark_match_ready(
    session: AsyncSession,
    match_id: UUID,
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
                == MatchStatus.READY
            ):
                return match_setup_read(
                    match
                )

            if (
                match.status
                != MatchStatus.DRAFT
            ):
                raise ConflictError(
                    "Only a draft match "
                    "can move to ready"
                )

            if (
                match.venue_id
                is None
            ):
                raise ValidationError(
                    "Venue is required "
                    "before the match "
                    "can be ready"
                )

            if (
                match.scheduled_at
                is None
            ):
                raise ValidationError(
                    "Scheduled date/time "
                    "is required before "
                    "the match can be ready"
                )

            await validate_match_references(
                repository,

                team_a_id=(
                    match.team_a_id
                ),

                team_b_id=(
                    match.team_b_id
                ),

                venue_id=(
                    match.venue_id
                ),

                tournament_id=(
                    match.tournament_id
                ),
            )

            readiness = evaluate_readiness(
                match
            )

            if not readiness.ready:
                raise ValidationError(
                    "Match setup is incomplete. "
                    "Missing: "
                    + ", ".join(
                        readiness.missing
                    )
                )

            team_a_memberships = (
                await repository
                .get_active_squad_memberships(
                    match.team_a_id,
                    playing_team_ids(
                        match,
                        match.team_a_id,
                    ),
                )
            )
            team_b_memberships = (
                await repository
                .get_active_squad_memberships(
                    match.team_b_id,
                    playing_team_ids(
                        match,
                        match.team_b_id,
                    ),
                )
            )

            if (
                len(
                    team_a_memberships
                )
                != match.players_per_side
            ):
                raise ValidationError(
                    "Team A playing team "
                    "contains a player who "
                    "is no longer in the "
                    "active squad"
                )

            if (
                len(
                    team_b_memberships
                )
                != match.players_per_side
            ):
                raise ValidationError(
                    "Team B playing team "
                    "contains a player who "
                    "is no longer in the "
                    "active squad"
                )

            # Stage 10:
            # A match cannot become READY until
            # incoming batters can be determined.
            team_a_selections = [
                selection
                for selection in match.players
                if selection.team_id == match.team_a_id
            ]
            team_b_selections = [
                selection
                for selection in match.players
                if selection.team_id == match.team_b_id
            ]

            validate_batting_order(
                team_a_selections,
                players_per_side=match.players_per_side,
            )
            validate_batting_order(
                team_b_selections,
                players_per_side=match.players_per_side,
            )

            first_innings = next(
                (
                    item
                    for item
                    in match.innings
                    if (
                        item.innings_number
                        == 1
                    )
                ),
                None,
            )

            if first_innings is None:
                raise ValidationError(
                    "Opening innings is required "
                    "before the match can be ready"
                )

            (
                batting_team_id,
                bowling_team_id,
            ) = derive_first_innings_teams(
                match
            )

            if (
                first_innings
                .batting_team_id
                != batting_team_id
                or first_innings
                .bowling_team_id
                != bowling_team_id
            ):
                raise ValidationError(
                    "First innings teams "
                    "do not match the "
                    "toss decision"
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
                first_innings.striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Configured striker "
                    "is no longer in the "
                    "batting team"
                )

            if (
                first_innings
                .non_striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Configured non-striker "
                    "is no longer in the "
                    "batting team"
                )

            if (
                first_innings
                .current_bowler_id
                not in bowling_xi
            ):
                raise ValidationError(
                    "Configured opening "
                    "bowler is no longer "
                    "in the bowling team"
                )

            match.status = MatchStatus.READY
            match.updated_at = datetime.now(UTC)
            await session.flush()

            add_audit_log(
                session,
                entity_type=("match"),
                entity_id=(match.id),
                action=(AuditAction.UPDATED),
                details={
                    "transition":
                        "draft_to_ready",

                    "status":
                        MatchStatus
                        .READY
                        .value,
                },
            )

            await session.flush()

        loaded = await reload_match(session, repository, match_id)
        return match_setup_read(loaded)

    except IntegrityError as error:
        raise integrity_conflict(error, "Match readiness") from error
