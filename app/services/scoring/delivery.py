from __future__ import annotations
import hashlib
import json
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
from app.services.scoring.state import current_state, ensure_scoreable, rebuild_innings_state
from app.services.scoring.wickets import validate_wicket
from app.domain.bowling import validate_bowler_quota


CLIENT_EVENT_CONSTRAINT = "uq_deliveries_match_client_event"


def request_fingerprint(payload: DeliveryCreate) -> str:
    """
    Canonical hash of the scoring event,
    excluding the idempotency key itself.
    """

    body = payload.model_dump(mode="json", exclude={"client_event_id"})
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_same_request(previous: Delivery, fingerprint: str) -> None:
    if previous.client_event_fingerprint != fingerprint:
        raise ConflictError(
            "This scoring event ID was already "
            "used for a different delivery."
        )


async def replay_delivery(
    repository: ScoringRepository,
    match_id: UUID,
    client_event_id: UUID,
    fingerprint: str,
) -> ScoringStateRead:
    """
    A verified identical retry returns the
    current authoritative state instead of
    recording a second ball.
    """

    previous = await repository.get_delivery_by_event_id(match_id, client_event_id)

    if previous is None:
        raise ConflictError("This scoring event has already been submitted.")

    ensure_same_request(previous, fingerprint)

    return await current_state(repository, match_id, "delivery replay")


async def record_delivery(session: AsyncSession, match_id: UUID, payload: DeliveryCreate) -> ScoringStateRead:
    repository = ScoringRepository(session)
    fingerprint = request_fingerprint(payload)

    try:

        async with service_transaction(session):
            innings = await repository.lock_current_innings(match_id)

            if innings is None:
                raise NotFoundError("First innings has not been configured")

            match = await repository.get_match(match_id)

            if match is None:
                raise NotFoundError("Match not found")

            # Checked before scoreability so a retry of the
            # ball that closed the innings still replays.
            if payload.client_event_id is not None:
                previous_event = await repository.get_delivery_by_event_id(
                    match_id,
                    payload.client_event_id,
                )

                if previous_event is not None:
                    ensure_same_request(previous_event, fingerprint)

                    return await current_state(
                        repository,
                        match_id,
                        "delivery replay",
                    )

            ensure_scoreable(match, innings)
            deliveries = await repository.get_recorded_deliveries_plain(innings.id)

            before = (
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

            if overs_complete(match, before.legal_balls):
                raise ConflictError(
                    "The configured "
                    "over limit has "
                    "been reached for "
                    "this innings"
                )

            if before.wickets >= max_wickets(match.players_per_side):
                raise ConflictError("The batting side is already all out")

            if innings.current_bowler_id is None:
                raise ValidationError("Current bowler is not configured")

            if bowler_change_required(
                legal_balls=before.legal_balls,
                balls_per_over=match.balls_per_over,
                previous_bowler_id=previous_over_bowler_id(deliveries),
                current_bowler_id=innings.current_bowler_id,
            ):

                raise ConflictError("Over complete. Select a different bowler for the next over")

            if innings.current_bowler_id in {
                before.striker_id,
                before.non_striker_id,
            }:
                raise ValidationError(
                    "A current batter cannot be "
                    "the bowling participant."
                )

            bowler_is_selected = (
                await repository.is_playing_team_player(
                    match_id=match.id,
                    team_id=innings.bowling_team_id,
                    player_id=innings.current_bowler_id,
                )
            )

            if not bowler_is_selected:
                raise ValidationError(
                    "Current bowler must belong "
                    "to the bowling playing XI."
                )

            components = delivery_components(payload)

            # Wides and no-balls do not consume quota, so a bowler
            # at the limit may still deliver an illegal ball.
            if components.is_legal_ball:
                validate_bowler_quota(
                    match=match,
                    deliveries=deliveries,
                    bowler_id=innings.current_bowler_id,
                )

            resolved_wicket = None

            if payload.wicket is not None:
                resolved_wicket = await validate_wicket(
                    repository,
                    match=match,
                    innings=innings,
                    before=before,
                    components=components,
                    wicket=payload.wicket,
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
                    resolved_wicket.dismissed_player_id
                    if resolved_wicket
                    else None
                ),

                fielder_id=(
                    wicket.fielder_id
                    if wicket
                    else None
                ),

                next_batter_id=(
                    resolved_wicket.next_batter_id
                    if resolved_wicket
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

                client_event_id=(
                    payload.client_event_id
                ),

                client_event_fingerprint=(
                    fingerprint
                    if payload.client_event_id
                    else None
                ),
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
                    resolved_wicket.dismissed_player_id
                    if resolved_wicket
                    else None
                ),

                next_batter_id=(
                    resolved_wicket.next_batter_id
                    if resolved_wicket
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

                    "client_event_id":
                        (
                            str(
                                payload
                                .client_event_id
                            )

                            if payload.client_event_id

                            else None
                        ),

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
                                resolved_wicket
                                .dismissed_player_id
                            )

                            if resolved_wicket

                            else None
                        ),

                    "next_batter_id":
                        (
                            str(
                                resolved_wicket
                                .next_batter_id
                            )

                            if (
                                resolved_wicket
                                and resolved_wicket
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

        # A concurrent identical request won the race;
        # the unique constraint is the final safeguard.
        if (
            payload.client_event_id is not None
            and CLIENT_EVENT_CONSTRAINT in str(error.orig)
        ):
            return await replay_delivery(
                repository,
                match_id,
                payload.client_event_id,
                fingerprint,
            )

        raise integrity_conflict(
            error,
            "Delivery",
        ) from error
