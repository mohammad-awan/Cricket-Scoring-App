from __future__ import annotations
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities.tournament_operations import TournamentDecision


def record_decision(
    session: AsyncSession,
    tournament_id: UUID,
    decision_type: str,
    reason: str,
    payload: dict,
    *,
    subject_id: UUID | None = None,
    actor_id: str | None = None,
) -> TournamentDecision:
    decision = TournamentDecision(
        tournament_id=tournament_id,
        decision_type=decision_type,
        subject_id=subject_id,
        actor_id=actor_id,
        reason=reason,
        payload=jsonable_encoder(payload),
    )
    session.add(decision)
    return decision


async def list_decisions(
    session: AsyncSession,
    tournament_id: UUID,
    decision_types: set[str] | None = None,
) -> list[TournamentDecision]:
    statement = select(TournamentDecision).where(
        TournamentDecision.tournament_id == tournament_id
    )

    if decision_types:
        statement = statement.where(
            TournamentDecision.decision_type.in_(sorted(decision_types))
        )

    return list(
        (
            await session.scalars(
                statement.order_by(
                    TournamentDecision.created_at,
                    TournamentDecision.id,
                )
            )
        ).all()
    )


def latest_by_key(
    decisions: list[TournamentDecision],
    key,
) -> dict:
    """Reduce an append-only decision stream to its latest entry per key.

    The decision log is immutable, so the current state of any
    organizer decision is the most recent event for its key.
    """

    latest: dict = {}

    for decision in decisions:
        latest[key(decision)] = decision

    return latest


async def current_state(
    session: AsyncSession,
    tournament_id: UUID,
    set_type: str,
    clear_type: str,
) -> TournamentDecision | None:
    """Latest set/clear decision for a tournament-wide flag."""

    decisions = await list_decisions(
        session,
        tournament_id,
        {set_type, clear_type},
    )

    if not decisions or decisions[-1].decision_type == clear_type:
        return None

    return decisions[-1]
