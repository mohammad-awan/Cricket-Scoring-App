from __future__ import annotations
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, Innings
from app.models.enums import InningsStatus, MatchStatus
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import NextInningsCreate, ScoringStateRead
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.scoring.calculations import max_innings
from app.services.scoring.chase import (
    chase_state,
    clear_match_result,
    close_innings,
    innings_finished,
)
from app.services.scoring.state import current_state, ensure_scoreable, rebuild_innings_state


async def end_innings(
    session: AsyncSession,
    match_id: UUID,
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

        if (
            match.total_overs
            is not None
        ):

            raise ConflictError(
                "Limited-overs "
                "innings end "
                "automatically when "
                "the over limit is "
                "reached"
            )

        deliveries = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        if not deliveries:

            raise ConflictError(
                "Record at least one "
                "delivery before "
                "ending the innings"
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

        innings_list = (
            await repository
            .list_innings(
                match.id
            )
        )

        totals = (
            await repository
            .delivery_totals(
                match.id
            )
        )

        chase = chase_state(
            match,
            innings,
            innings_list,
            totals,
        )

        close_innings(
            match,
            innings,

            wickets=(
                derived.wickets
            ),

            chase=(
                chase
            ),
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
                    "innings_ended",

                "innings_number":
                    innings
                    .innings_number,
            },
        )

        await session.flush()

    return await current_state(
        repository,
        match_id,
        "ending the innings",
    )


async def start_next_innings(
    session: AsyncSession,
    match_id: UUID,
    payload: NextInningsCreate,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    try:

        async with service_transaction(
            session
        ):

            previous = (
                await repository
                .lock_current_innings(
                    match_id
                )
            )

            if previous is None:

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

            if (
                match.status
                in {
                    MatchStatus.COMPLETED,
                    MatchStatus.ABANDONED,
                }
            ):

                raise ConflictError(
                    "The match is "
                    "already finished"
                )

            next_number = (
                previous
                .innings_number
                + 1
            )

            if (
                next_number
                > max_innings(
                    match
                    .innings_per_team
                )
            ):

                raise ConflictError(
                    "All innings for "
                    "this match have "
                    "been played"
                )

            deliveries = (
                await repository
                .get_recorded_deliveries_plain(
                    previous.id
                )
            )

            derived = (
                rebuild_innings_state(
                    previous,
                    deliveries,
                    await repository.get_official_retirements(previous.id),
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
            )

            innings_list = (
                await repository
                .list_innings(
                    match.id
                )
            )

            totals = (
                await repository
                .delivery_totals(
                    match.id
                )
            )

            chase = chase_state(
                match,
                previous,
                innings_list,
                totals,
            )

            if not innings_finished(
                match,
                previous,
                derived.legal_balls,
                derived.wickets,
                chase,
            ):

                raise ConflictError(
                    f"Innings "
                    f"{previous.innings_number} "
                    "is still in progress"
                )

            batting_team_id = (
                previous
                .bowling_team_id
            )

            bowling_team_id = (
                previous
                .batting_team_id
            )

            for (
                player_id,
                team_id,
                label,
            ) in (
                (
                    payload
                    .striker_id,

                    batting_team_id,

                    "Striker",
                ),

                (
                    payload
                    .non_striker_id,

                    batting_team_id,

                    "Non-striker",
                ),

                (
                    payload
                    .opening_bowler_id,

                    bowling_team_id,

                    "Opening bowler",
                ),
            ):

                side = (
                    "batting"

                    if (
                        team_id
                        == batting_team_id
                    )

                    else "bowling"
                )

                belongs = (
                    await repository
                    .is_playing_team_player(
                        match_id=(
                            match.id
                        ),

                        team_id=(
                            team_id
                        ),

                        player_id=(
                            player_id
                        ),
                    )
                )

                if not belongs:

                    raise ValidationError(
                        f"{label} must "
                        f"belong to the "
                        f"{side} team's "
                        "playing team"
                    )

            previous.status = (
                InningsStatus.COMPLETED
            )

            innings = Innings(
                match_id=(
                    match.id
                ),

                innings_number=(
                    next_number
                ),

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
                innings
            )

            clear_match_result(
                match
            )

            match.status = (
                MatchStatus.LIVE
            )

            await session.flush()

            add_audit_log(
                session,

                entity_type=(
                    "innings"
                ),

                entity_id=(
                    innings.id
                ),

                action=(
                    AuditAction.CREATED
                ),

                details={
                    "setup":
                        "next_innings",

                    "innings_number":
                        next_number,

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

        return await current_state(
            repository,
            match_id,
            "starting the innings",
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Innings",
        ) from error
