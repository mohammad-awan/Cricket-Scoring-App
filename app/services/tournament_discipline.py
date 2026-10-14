"""Stage 11 disciplinary point deductions.

Deductions are append-only: a mistaken one is revoked with a reason rather
than edited or deleted, and every change is written to the tournament audit
trail. Stage 13 subtracts active deductions when computing standings.
"""

from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Match, TournamentPointDeduction, TournamentStatus
from app.repositories.tournaments import TournamentRepository
from app.schemas.tournaments import PointDeductionCreate
from app.services.tournaments import (
    _refreshed,
    get_tournament,
    locked_tournament,
    require_membership,
    tournament_audit,
    tournament_transaction,
)


# Deductions need a competition with entrants; closed records stay frozen.
DEDUCTION_LOCKED_STATUSES = frozenset(
    {
        TournamentStatus.DRAFT,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    }
)


async def list_point_deductions(
    session: AsyncSession,
    tournament_id: UUID,
    include_revoked: bool = True,
) -> list[TournamentPointDeduction]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_deductions(
        tournament_id,
        include_revoked=include_revoked,
    )


async def create_point_deduction(
    session: AsyncSession,
    tournament_id: UUID,
    payload: PointDeductionCreate,
    *,
    actor_id: str | None = None,
) -> TournamentPointDeduction:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament point deduction"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status in DEDUCTION_LOCKED_STATUSES:
            raise ConflictError(
                f"Points cannot be deducted while the tournament is {tournament.status.value}"
            )

        membership = await require_membership(
            repository,
            tournament_id,
            payload.tournament_team_id,
        )
        if membership.registration_status != "approved":
            raise ConflictError("Points can only be deducted from approved teams")

        if payload.match_id is not None:
            match = await session.get(Match, payload.match_id)
            if match is None or match.tournament_id != tournament_id:
                raise NotFoundError("Match not found in this tournament")

            if membership.team_id not in {match.team_a_id, match.team_b_id}:
                raise ValidationError("The team did not play in that match")

        deduction = TournamentPointDeduction(
            tournament_id=tournament_id,
            tournament_team_id=membership.id,
            match_id=payload.match_id,
            points=payload.points,
            reason=payload.reason,
            created_by=actor_id,
        )
        session.add(deduction)
        await session.flush()

        tournament_audit(
            session,
            tournament_id,
            "points_deducted",
            {
                "deduction_id": str(deduction.id),
                "membership_id": str(membership.id),
                "points": payload.points,
                "match_id": str(payload.match_id) if payload.match_id else None,
                "reason": payload.reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, deduction)


async def revoke_point_deduction(
    session: AsyncSession,
    tournament_id: UUID,
    deduction_id: UUID,
    reason: str,
    *,
    actor_id: str | None = None,
) -> TournamentPointDeduction:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament point deduction"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status == TournamentStatus.ARCHIVED:
            raise ConflictError("Archived tournaments are read-only")

        deduction = await repository.get_deduction_locked(tournament_id, deduction_id)
        if deduction is None:
            raise NotFoundError("Point deduction not found")

        if deduction.revoked_at is not None:
            return deduction

        deduction.revoked_at = datetime.now(UTC)
        deduction.revoked_by = actor_id
        deduction.revoked_reason = reason

        tournament_audit(
            session,
            tournament_id,
            "point_deduction_revoked",
            {
                "deduction_id": str(deduction_id),
                "points": deduction.points,
                "reason": reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, deduction)
