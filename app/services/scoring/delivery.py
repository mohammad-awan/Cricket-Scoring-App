from __future__ import annotations
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, Delivery
from app.models.enums import DeliveryStatus, InningsStatus, MatchStatus
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import DeliveryCreate, ScoringStateRead
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.scoring.calculations import (
    overs_complete,
    post_delivery_batters,
    ball_position,
    bowler_change_required,
    delivery_components,
    max_wickets,
    previous_over_bowler_id,
)
from app.services.scoring.chase import chase_state, close_innings, innings_finished
from app.services.scoring.state import current_state, ensure_scoreable, rebuild_from_deliveries
from app.services.scoring.wickets import validate_wicket


async def record_delivery(
    session: AsyncSession,
    match_id: UUID,
    payload: DeliveryCreate,
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

            before = (
                rebuild_from_deliveries(
                    innings,
                    deliveries,
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
            )

            if overs_complete(
                match,
                before.legal_balls,
            ):

                raise ConflictError(
                    "The configured "
                    "over limit has "
                    "been reached for "
                    "this innings"
                )

            if (
                before.wickets
                >= max_wickets(
                    match
                    .players_per_side
                )
            ):

                raise ConflictError(
                    "The batting side "
                    "is already all out"
                )

            if (
                innings.current_bowler_id
                is None
            ):

                raise ValidationError(
                    "Current bowler "
                    "is not configured"
                )

            if bowler_change_required(
                legal_balls=(
                    before.legal_balls
                ),

                balls_per_over=(
                    match
                    .balls_per_over
                ),

                previous_bowler_id=(
                    previous_over_bowler_id(
                        deliveries
                    )
                ),

                current_bowler_id=(
                    innings
                    .current_bowler_id
                ),
            ):

                raise ConflictError(
                    "Over complete. "
                    "Select a different "
                    "bowler for the "
                    "next over"
                )

            components = (
                delivery_components(
                    payload
                )
            )

            if (
                payload.wicket
                is not None
            ):

                await validate_wicket(
                    repository,

                    match=match,

                    innings=innings,

                    before=before,

                    components=(
                        components
                    ),

                    wicket=(
                        payload.wicket
                    ),
                )

            (
                over_number,
                ball_number,
            ) = ball_position(
                before.legal_balls,
                match.balls_per_over,
            )

            sequence = (
                await repository
                .next_delivery_number(
                    innings.id
                )
            )

            wicket = (
                payload.wicket
            )

            delivery = Delivery(
                match_id=(
                    match.id
                ),

                innings_id=(
                    innings.id
                ),

                delivery_number=(
                    sequence
                ),

                over_number=(
                    over_number
                ),

                ball_number=(
                    ball_number
                ),

                striker_id=(
                    before.striker_id
                ),

                non_striker_id=(
                    before
                    .non_striker_id
                ),

                bowler_id=(
                    innings
                    .current_bowler_id
                ),

                batter_runs=(
                    components
                    .batter_runs
                ),

                extra_runs=(
                    components
                    .extra_runs
                ),

                wide_runs=(
                    components
                    .wide_runs
                ),

                no_ball_runs=(
                    components
                    .no_ball_runs
                ),

                bye_runs=(
                    components
                    .bye_runs
                ),

                leg_bye_runs=(
                    components
                    .leg_bye_runs
                ),

                total_runs=(
                    components
                    .total_runs
                ),

                is_legal_ball=(
                    components
                    .is_legal_ball
                ),

                wicket_type=(
                    wicket.wicket_type
                    if wicket
                    else None
                ),

                dismissed_player_id=(
                    wicket
                    .dismissed_player_id
                    if wicket
                    else None
                ),

                fielder_id=(
                    wicket.fielder_id
                    if wicket
                    else None
                ),

                next_batter_id=(
                    wicket
                    .next_batter_id
                    if wicket
                    else None
                ),

                wicket_end=(
                    wicket.wicket_end
                    if wicket
                    else None
                ),

                status=(
                    DeliveryStatus
                    .RECORDED
                ),

                actor_id=None,
            )

            session.add(
                delivery
            )

            await session.flush()

            after_legal = (
                before.legal_balls

                + (
                    1
                    if components
                    .is_legal_ball
                    else 0
                )
            )

            after_wickets = (
                before.wickets

                + (
                    1
                    if wicket
                    is not None
                    else 0
                )
            )

            (
                after_striker,
                after_non_striker,
            ) = post_delivery_batters(
                striker_id=(
                    before.striker_id
                ),

                non_striker_id=(
                    before
                    .non_striker_id
                ),

                running_runs=(
                    components
                    .running_runs
                ),

                is_legal_ball=(
                    components
                    .is_legal_ball
                ),

                legal_balls_after=(
                    after_legal
                ),

                balls_per_over=(
                    match
                    .balls_per_over
                ),

                dismissed_player_id=(
                    wicket
                    .dismissed_player_id
                    if wicket
                    else None
                ),

                next_batter_id=(
                    wicket
                    .next_batter_id
                    if wicket
                    else None
                ),

                wicket_end=(
                    wicket.wicket_end
                    if wicket
                    else None
                ),
            )

            # Rebuildable caches.
            innings.total_runs = (
                before.total_runs
                + components.total_runs
            )

            innings.wickets = (
                after_wickets
            )

            innings.legal_balls = (
                after_legal
            )

            innings.striker_id = (
                after_striker
            )

            innings.non_striker_id = (
                after_non_striker
            )

            innings.status = (
                InningsStatus.LIVE
            )

            if (
                match.status
                == MatchStatus.READY
            ):

                match.status = (
                    MatchStatus.LIVE
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

            if innings_finished(
                match,
                innings,
                after_legal,
                after_wickets,
                chase,
            ):

                close_innings(
                    match,
                    innings,

                    wickets=(
                        after_wickets
                    ),

                    chase=(
                        chase
                    ),
                )

            add_audit_log(
                session,

                entity_type=(
                    "delivery"
                ),

                entity_id=(
                    delivery.id
                ),

                action=(
                    AuditAction.CREATED
                ),

                details={
                    "match_id":
                        str(
                            match.id
                        ),

                    "innings_id":
                        str(
                            innings.id
                        ),

                    "sequence":
                        sequence,

                    "over_number":
                        over_number,

                    "ball_number":
                        ball_number,

                    "batter_runs":
                        components
                        .batter_runs,

                    "wide_runs":
                        components
                        .wide_runs,

                    "no_ball_runs":
                        components
                        .no_ball_runs,

                    "bye_runs":
                        components
                        .bye_runs,

                    "leg_bye_runs":
                        components
                        .leg_bye_runs,

                    "total_runs":
                        components
                        .total_runs,

                    "wicket_type":
                        (
                            wicket
                            .wicket_type
                            .value

                            if wicket

                            else None
                        ),

                    "dismissed_player_id":
                        (
                            str(
                                wicket
                                .dismissed_player_id
                            )

                            if wicket

                            else None
                        ),

                    "next_batter_id":
                        (
                            str(
                                wicket
                                .next_batter_id
                            )

                            if (
                                wicket
                                and wicket
                                .next_batter_id
                            )

                            else None
                        ),
                },
            )

            await session.flush()

        return await current_state(
            repository,
            match_id,
            "delivery commit",
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Delivery",
        ) from error
