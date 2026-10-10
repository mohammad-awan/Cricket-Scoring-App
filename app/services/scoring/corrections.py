from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models import AuditAction, DeliveryCorrection
from app.models.enums import CorrectionType, DeliveryStatus, InningsStatus, MatchStatus
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import DeliveryUndo, ScoringStateRead
from app.services.common import add_audit_log, service_transaction
from app.services.scoring.chase import (
    chase_state,
    clear_match_result,
    close_innings,
    innings_finished,
)
from app.services.scoring.state import current_state, rebuild_from_deliveries
from app.services.scoring.types import DerivedState


async def undo_delivery(
    session: AsyncSession,
    match_id: UUID,
    delivery_id: UUID,
    payload: DeliveryUndo,
) -> ScoringStateRead:
    """
    Safe Stage 5 undo.

    We intentionally only allow the
    latest official delivery to be
    undone. That prevents a scorer
    from voiding an old event while
    leaving later participant states
    inconsistent.

    History is never deleted.
    """

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

        delivery = (
            await repository
            .get_delivery_for_update(
                match_id=(
                    match_id
                ),

                delivery_id=(
                    delivery_id
                ),
            )
        )

        if delivery is None:

            raise NotFoundError(
                "Delivery not found"
            )

        if (
            delivery.innings_id
            != innings.id
        ):

            raise ConflictError(
                "Only the current "
                "innings can be "
                "corrected in Stage 5"
            )

        if (
            delivery.status
            != DeliveryStatus.RECORDED
        ):

            raise ConflictError(
                "This delivery has "
                "already been voided"
            )

        latest = (
            await repository
            .last_recorded_delivery(
                innings.id
            )
        )

        if (
            latest is None
            or latest.id
            != delivery.id
        ):

            raise ConflictError(
                "Stage 5 safe undo "
                "can only void the "
                "most recent official "
                "delivery"
            )

        # ======================
        # PRESERVE HISTORY
        # ======================

        delivery.status = (
            DeliveryStatus.VOID
        )

        correction = (
            DeliveryCorrection(
                delivery_id=(
                    delivery.id
                ),

                correction_type=(
                    CorrectionType.VOID
                ),

                reason=(
                    payload.reason
                ),

                actor_id=None,
            )
        )

        session.add(
            correction
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
                AuditAction.CORRECTED
            ),

            details={
                "correction_type":
                    CorrectionType
                    .VOID
                    .value,

                "reason":
                    payload.reason,

                "sequence":
                    delivery
                    .delivery_number,
            },
        )

        await session.flush()

        # ======================
        # REBUILD STATE
        # ======================

        remaining = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        if remaining:

            rebuilt = (
                rebuild_from_deliveries(
                    innings,
                    remaining,
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
            )

        else:

            # The now-void delivery
            # stores the exact state
            # immediately before it.
            rebuilt = DerivedState(
                total_runs=0,

                legal_balls=0,

                wickets=0,

                striker_id=(
                    delivery
                    .striker_id
                ),

                non_striker_id=(
                    delivery
                    .non_striker_id
                ),
            )

        innings.total_runs = (
            rebuilt.total_runs
        )

        innings.wickets = (
            rebuilt.wickets
        )

        innings.legal_balls = (
            rebuilt.legal_balls
        )

        innings.striker_id = (
            rebuilt.striker_id
        )

        innings.non_striker_id = (
            rebuilt.non_striker_id
        )

        # This is exactly the bowler
        # selected immediately before
        # the voided event.
        innings.current_bowler_id = (
            delivery.bowler_id
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

        # Important: undo may reopen
        # an innings or completed match.
        innings.status = (
            InningsStatus.LIVE
            if remaining
            else InningsStatus.PENDING
        )

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

                wickets=(
                    rebuilt.wickets
                ),

                chase=(
                    chase
                ),
            )

        else:

            clear_match_result(
                match
            )

            match.status = (
                MatchStatus.READY

                if (
                    innings.innings_number
                    == 1
                    and not remaining
                )

                else MatchStatus.LIVE
            )

        await session.flush()

    return await current_state(
        repository,
        match_id,
        "delivery undo",
    )
