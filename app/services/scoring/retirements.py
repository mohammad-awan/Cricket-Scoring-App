from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.domain.batting_order import select_next_batter, validate_batting_order
from app.domain.retirements import (
    crease_after_retirement,
    validate_retiring_player,
)
from app.models import AuditAction, BatterRetirement
from app.models.enums import DeliveryStatus, InningsStatus, MatchStatus, RetirementType
from app.repositories.scoring import ScoringRepository
from app.schemas.retirements import RetirementCreate, RetirementUndo
from app.schemas.scoring import ScoringStateRead
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.scoring.calculations import max_wickets, overs_complete
from app.domain.playing_side import batting_side_size, minimum_players
from app.services.scoring.chase import (
    chase_state,
    clear_match_result,
    close_innings,
    innings_finished,
)
from app.services.scoring.state import (
    batter_status,
    current_state,
    ensure_scoreable,
    load_innings_state,
    rebuild_innings_state,
)


async def create_retirement(
    session: AsyncSession,
    match_id: UUID,
    payload: RetirementCreate,
) -> ScoringStateRead:
    """
    Record a batter retiring between deliveries.

    Decisions are made from the locked, replayed
    innings state, never from the client's view of
    who is batting.
    """

    repository = ScoringRepository(session)

    try:

        async with service_transaction(session):
            innings = await repository.lock_current_innings(match_id)

            if innings is None:
                raise NotFoundError("First innings has not been configured")

            match = await repository.get_match(match_id)

            if match is None:
                raise NotFoundError("Match not found")

            ensure_scoreable(match, innings)

            (
                deliveries,
                retirements,
                before,
            ) = await load_innings_state(
                repository,
                match=match,
                innings=innings,
            )

            if overs_complete(match, before.legal_balls):
                raise ConflictError("The configured over limit has been reached for this innings")

            wicket_limit = max_wickets(batting_side_size(match, innings))

            if before.wickets >= wicket_limit:
                raise ConflictError("The batting side is already all out")

            validate_retiring_player(
                payload.player_id,
                striker_id=before.striker_id,
                non_striker_id=before.non_striker_id,
            )

            selections = await repository.get_playing_xi(match.id, innings.batting_team_id)
            ordered_ids = validate_batting_order(
                selections,
                players_per_side=match.players_per_side,
                minimum_players=minimum_players(match),
            )

            delivery_dismissed, retired = batter_status(deliveries, retirements, before)

            is_out = payload.retirement_type == RetirementType.OUT
            wickets_after = before.wickets + (1 if is_out else 0)

            # A retired-hurt batter with no one left to
            # replace them is rejected by select_next_batter.
            replacement_id = select_next_batter(
                ordered_ids,
                striker_id=before.striker_id,
                non_striker_id=before.non_striker_id,
                dismissed_player_ids=delivery_dismissed | retired.retired_out_ids,
                dismissed_player_id=payload.player_id,
                selection_mode=payload.selection_mode,
                manual_player_id=payload.replacement_player_id,
                final_wicket=is_out and wickets_after >= wicket_limit,
                resumable_player_ids=set(retired.retired_hurt_ids),
            )

            striker_after, non_striker_after = crease_after_retirement(
                striker_id=before.striker_id,
                non_striker_id=before.non_striker_id,
                retiring_player_id=payload.player_id,
                replacement_player_id=replacement_id,
            )

            retirement = BatterRetirement(
                match_id=match.id,
                innings_id=innings.id,
                event_number=await repository.next_retirement_number(innings.id),
                after_delivery_number=(
                    deliveries[-1].delivery_number
                    if deliveries
                    else 0
                ),
                player_id=payload.player_id,
                retirement_type=payload.retirement_type,
                replacement_player_id=replacement_id,
                selection_mode=payload.selection_mode,
                striker_before_id=before.striker_id,
                non_striker_before_id=before.non_striker_id,
                striker_after_id=striker_after,
                non_striker_after_id=non_striker_after,
                reason=payload.reason,
                status=DeliveryStatus.RECORDED,
                actor_id=None,
            )

            session.add(retirement)
            await session.flush()

            # Rebuildable caches.
            innings.wickets = wickets_after
            innings.striker_id = striker_after
            innings.non_striker_id = non_striker_after

            if wickets_after >= wicket_limit:
                innings_list = await repository.list_innings(match.id)
                totals = await repository.delivery_totals(match.id)
                chase = chase_state(match, innings, innings_list, totals)

                if innings_finished(
                    match,
                    innings,
                    before.legal_balls,
                    wickets_after,
                    chase,
                ):
                    close_innings(
                        match,
                        innings,
                        wickets=wickets_after,
                        chase=chase,
                    )

            add_audit_log(
                session,
                entity_type="batter_retirement",
                entity_id=retirement.id,
                action=AuditAction.CREATED,
                details={
                    "match_id": str(match.id),
                    "innings_id": str(innings.id),
                    "event_number": retirement.event_number,
                    "after_delivery_number": retirement.after_delivery_number,
                    "player_id": str(payload.player_id),
                    "retirement_type": payload.retirement_type.value,
                    "selection_mode": payload.selection_mode,
                    "replacement_player_id": (
                        str(replacement_id)
                        if replacement_id
                        else None
                    ),
                    "reason": payload.reason,
                },
            )

            await session.flush()

    except IntegrityError as error:
        raise integrity_conflict(error, "Retirement") from error

    return await current_state(repository, match_id, "retirement")


async def undo_retirement(
    session: AsyncSession,
    match_id: UUID,
    retirement_id: UUID,
    payload: RetirementUndo,
) -> ScoringStateRead:
    """
    Void the latest official retirement.

    Like delivery undo, only the most recent official
    event can be corrected, so later participant
    states never depend on a voided event. The row is
    kept for the audit trail.
    """

    repository = ScoringRepository(session)

    async with service_transaction(session):
        innings = await repository.lock_current_innings(match_id)

        if innings is None:
            raise NotFoundError("First innings has not been configured")

        match = await repository.get_match(match_id)

        if match is None:
            raise NotFoundError("Match not found")

        retirement = await repository.get_retirement_for_update(
            match_id=match_id,
            retirement_id=retirement_id,
        )

        if retirement is None:
            raise NotFoundError("Retirement not found")

        if retirement.innings_id != innings.id:
            raise ConflictError("Only retirements in the current innings can be undone")

        if retirement.status != DeliveryStatus.RECORDED:
            raise ConflictError("This retirement has already been voided")

        deliveries = await repository.get_recorded_deliveries_plain(innings.id)
        retirements = await repository.get_official_retirements(innings.id)

        last_delivery_number = deliveries[-1].delivery_number if deliveries else 0

        if (
            retirements[-1].id != retirement.id
            or retirement.after_delivery_number < last_delivery_number
        ):
            raise ConflictError(
                "Only the most recent scoring event can be undone. "
                "Undo the later deliveries or retirements first"
            )

        retirement.status = DeliveryStatus.VOID
        retirement.void_reason = payload.reason
        retirement.voided_at = datetime.now(timezone.utc)

        add_audit_log(
            session,
            entity_type="batter_retirement",
            entity_id=retirement.id,
            action=AuditAction.CORRECTED,
            details={
                "correction_type": "void",
                "reason": payload.reason,
                "event_number": retirement.event_number,
            },
        )

        await session.flush()

        # With no deliveries the innings cache is the
        # replay base, so restore the pre-event crease.
        innings.striker_id = retirement.striker_before_id
        innings.non_striker_id = retirement.non_striker_before_id

        rebuilt = rebuild_innings_state(
            innings,
            deliveries,
            retirements[:-1],
            balls_per_over=match.balls_per_over,
        )

        innings.total_runs = rebuilt.total_runs
        innings.wickets = rebuilt.wickets
        innings.legal_balls = rebuilt.legal_balls
        innings.striker_id = rebuilt.striker_id
        innings.non_striker_id = rebuilt.non_striker_id

        # Undoing a final retired out may reopen
        # the innings or a completed match.
        innings.status = (
            InningsStatus.LIVE
            if deliveries
            else InningsStatus.PENDING
        )

        innings_list = await repository.list_innings(match.id)
        totals = await repository.delivery_totals(match.id)
        chase = chase_state(match, innings, innings_list, totals)

        if innings_finished(
            match,
            innings,
            rebuilt.legal_balls,
            rebuilt.wickets,
            chase,
        ):
            close_innings(
                match,
                innings,
                wickets=rebuilt.wickets,
                chase=chase,
            )

        else:
            clear_match_result(match)

            match.status = (
                MatchStatus.READY
                if innings.innings_number == 1 and not deliveries
                else MatchStatus.LIVE
            )

        await session.flush()

    return await current_state(repository, match_id, "retirement undo")
