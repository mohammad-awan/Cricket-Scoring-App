"""Award administration: confirmation, overrides, votes, publication.

Policy:

* Every award is confirmed explicitly by an organizer with a reason.
  ``selection_method`` is ``statistical`` only when the organizer
  confirms the unambiguous computed leader; everything else is
  ``manual`` and its evidence records the basis (organizer selection,
  override of the computed leader, or committee vote).
* Eligibility constraints (emerging player age, best-economy minimum
  balls, Player of the Tournament minimum matches, participation in an
  official match) cannot be overridden.
* Published awards are frozen: unpublish them (with a reason) before
  changing anything. Finalization requires published awards.
"""

from __future__ import annotations
from datetime import UTC, date, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Match, MatchPlayer, MatchStatus, Player, Tournament, TournamentStatus, TournamentTeam
from app.models.entities.fixtures import Fixture, FixtureGenerationRun
from app.models.entities.tournament_operations import TournamentAward
from app.repositories.tournaments import TournamentRepository
from app.schemas.tournament_awards import AwardSettings
from app.services.tournament_awards import (
    COMPUTED_AWARDS,
    PLAYER_OF_MATCH_PREFIX,
    SETTINGS_DECISION,
    VOTE_DECISION,
    emerging_eligibility,
    get_award_settings,
    tournament_award_candidates,
    vote_tally,
)
from app.services.tournament_decisions import current_state, record_decision
from app.services.tournament_statistics import official_completed_match_ids
from app.services.tournaments import locked_tournament, tournament_audit, tournament_transaction


PUBLISHED = "awards_published"
UNPUBLISHED = "awards_unpublished"
CLOSED_STATUSES = {TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED, TournamentStatus.CANCELLED}


def serialize_award(award: TournamentAward) -> dict:
    return {
        "id": award.id,
        "tournament_id": award.tournament_id,
        "award_code": award.award_code,
        "category": "player_of_match" if award.award_code.startswith(PLAYER_OF_MATCH_PREFIX) else (
            "computed" if award.award_code in COMPUTED_AWARDS else "organizer_defined"
        ),
        "title": COMPUTED_AWARDS.get(award.award_code, award.award_code.replace("_", " ").title()),
        "player_id": award.player_id,
        "team_id": award.team_id,
        "status": award.status,
        "selection_method": award.selection_method,
        "basis": (award.evidence or {}).get("basis"),
        "override": (award.evidence or {}).get("override", False),
        "reason": award.reason,
        "evidence": award.evidence,
        "confirmed_by": award.confirmed_by,
        "confirmed_at": award.confirmed_at,
    }


async def list_confirmed_awards(session: AsyncSession, tournament_id: UUID) -> list[TournamentAward]:
    if await session.get(Tournament, tournament_id) is None:
        raise NotFoundError("Tournament not found")

    return list(
        (
            await session.scalars(
                select(TournamentAward)
                .where(TournamentAward.tournament_id == tournament_id, TournamentAward.status == "confirmed")
                .order_by(TournamentAward.award_code)
            )
        ).all()
    )


async def publication_state(session: AsyncSession, tournament_id: UUID) -> dict:
    decision = await current_state(session, tournament_id, PUBLISHED, UNPUBLISHED)
    return {
        "published": decision is not None,
        "published_at": decision.created_at if decision else None,
        "published_reason": decision.reason if decision else None,
        "snapshot": decision.payload if decision else None,
    }


async def _editable(session: AsyncSession, tournament_id: UUID) -> Tournament:
    tournament = await locked_tournament(TournamentRepository(session), tournament_id)

    if tournament.status in CLOSED_STATUSES:
        raise ConflictError("Awards cannot be changed in a closed tournament. Reopen it first.")

    if (await publication_state(session, tournament_id))["published"]:
        raise ConflictError("Awards are published and frozen. Unpublish them with a reason first.")

    return tournament


async def _official_match_ids(session: AsyncSession, tournament_id: UUID) -> list[UUID]:
    match_ids = await official_completed_match_ids(session, tournament_id)
    if not match_ids:
        raise ValidationError("No official completed tournament matches")
    return match_ids


async def _check_recipient(session: AsyncSession, tournament_id: UUID, player_id: UUID | None, team_id: UUID | None) -> None:
    if team_id is not None:
        membership = await session.scalar(
            select(TournamentTeam.id).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.team_id == team_id,
                TournamentTeam.registration_status == "approved",
                TournamentTeam.is_reserve.is_(False),
            )
        )
        if membership is None:
            raise ValidationError("Award recipient team is not an approved entrant")

    if player_id is not None:
        match_ids = await _official_match_ids(session, tournament_id)
        participant = await session.scalar(
            select(MatchPlayer.id).where(MatchPlayer.match_id.in_(match_ids), MatchPlayer.player_id == player_id).limit(1)
        )
        if participant is None:
            raise ValidationError("Player must have participated in an official completed tournament match")


def _check_award_eligibility(award_code: str, player_id: UUID | None, computed: dict | None, settings: AwardSettings) -> None:
    if computed is None or player_id is None:
        return

    if award_code == "emerging_player":
        if not settings.emerging.configured:
            raise ConflictError("Configure emerging player eligibility before confirming this award")
        excluded = {row["player_id"]: row["reason"] for row in computed.get("excluded", [])}
        eligible = {row["player_id"] for row in computed.get("all_candidates", [])}
        if player_id not in eligible:
            raise ValidationError(f"Player is not eligible for Emerging Player: {excluded.get(player_id, 'not eligible')}")

    if award_code in {"best_economy", "player_of_tournament"}:
        if player_id not in {row["player_id"] for row in computed.get("all_candidates", [])}:
            raise ValidationError("Player does not meet the eligibility thresholds configured for this award")


def award_decision(
    basis: str,
    recipient_id: UUID,
    computed: dict | None,
    *,
    voting_enabled: bool = False,
    tally: dict | None = None,
    evidence: dict | None = None,
) -> tuple[str, dict]:
    """Pure confirmation policy: selection method plus auditable evidence.

    No algorithm picks the recipient; this only classifies the organizer's
    explicit choice and rejects claims that the evidence does not support.
    """

    details = dict(evidence or {})
    details["basis"] = basis
    method = "manual"

    if computed is not None:
        candidates = computed["all_candidates"]
        leader = candidates[0] if candidates else None
        details["computed_leader"] = (
            {"player_id": str(leader["player_id"]), "player_name": leader["player_name"]} if leader else None
        )
        details["leader_unambiguous"] = computed["leader_unambiguous"]
        details["recipient_computed_rank"] = next(
            (index + 1 for index, row in enumerate(candidates) if row["player_id"] == recipient_id), None
        )
        details["override"] = leader is None or leader["player_id"] != recipient_id
        details["ranking_basis"] = computed["basis"]

    if basis == "statistical_leader":
        if computed is None:
            raise ValidationError("Only computed awards can be confirmed as the statistical leader")
        if details["override"] or not computed["leader_unambiguous"]:
            raise ConflictError(
                "The recipient is not the unambiguous computed leader; "
                "confirm as an organizer selection with an explanation"
            )
        method = "statistical"

    if basis == "committee_vote":
        if not voting_enabled:
            raise ConflictError("Committee voting is not enabled for this tournament")
        if tally is None or tally["unique_leader"] != str(recipient_id):
            raise ConflictError("The recipient is not the unique committee vote winner")
        details["committee_tally"] = tally["ranking"]

    return method, details


async def _computed_award(session: AsyncSession, tournament_id: UUID, award_code: str, settings: AwardSettings) -> dict | None:
    if award_code not in COMPUTED_AWARDS:
        return None

    # Rank every candidate (not only the display limit) for eligibility checks.
    full = settings.model_copy(update={"candidates_limit": 10_000})
    result = await tournament_award_candidates(session, tournament_id, full)
    award = next(item for item in result["awards"] if item["award_code"] == award_code)
    return {**award, "all_candidates": award["candidates"]}


async def confirm_award(
    session: AsyncSession,
    tournament_id: UUID,
    award_code: str,
    *,
    player_id: UUID | None = None,
    team_id: UUID | None = None,
    reason: str,
    basis: str = "organizer_selection",
    match_id: UUID | None = None,
    actor_id: str | None = None,
    selection_method: str | None = None,
    evidence: dict | None = None,
) -> TournamentAward:
    award_code = award_code.strip().lower()
    reason = reason.strip()

    if not award_code or len(award_code) > 60:
        raise ValidationError("Invalid award code")
    if (player_id is None) == (team_id is None):
        raise ValidationError("Specify exactly one recipient: player_id or team_id")
    if len(reason) < 10:
        raise ValidationError("Award reason must have at least 10 characters")
    if basis not in {"organizer_selection", "statistical_leader", "committee_vote"}:
        raise ValidationError("Invalid award basis")
    if award_code.startswith(PLAYER_OF_MATCH_PREFIX) and match_id is None:
        raise ValidationError("Use the Player of the Match endpoint for match awards")

    async with tournament_transaction(session, "Tournament award"):
        await _editable(session, tournament_id)
        await _check_recipient(session, tournament_id, player_id, team_id)
        settings = await get_award_settings(session, tournament_id)
        computed = await _computed_award(session, tournament_id, award_code, settings)

        if computed is not None and team_id is not None:
            raise ValidationError("Computed awards are individual player awards")

        _check_award_eligibility(award_code, player_id, computed, settings)
        tally = await vote_tally(session, tournament_id, award_code) if basis == "committee_vote" else None
        method, details = award_decision(
            basis, player_id or team_id, computed, voting_enabled=settings.voting_enabled, tally=tally, evidence=evidence
        )

        if match_id is not None:
            details["match_id"] = str(match_id)

        award = await session.scalar(
            select(TournamentAward)
            .where(TournamentAward.tournament_id == tournament_id, TournamentAward.award_code == award_code)
            .with_for_update()
        )

        if award is not None and award.status == "confirmed":
            raise ConflictError("Award already confirmed. Revoke it with a reason first.")

        if award is None:
            award = TournamentAward(tournament_id=tournament_id, award_code=award_code)
            session.add(award)

        award.player_id = player_id
        award.team_id = team_id
        award.reason = reason
        award.selection_method = selection_method or method
        award.evidence = details
        award.status = "confirmed"
        award.confirmed_by = actor_id
        award.confirmed_at = datetime.now(UTC)

        tournament_audit(
            session, tournament_id, "award_confirmed",
            {"award_code": award_code, "player_id": str(player_id) if player_id else None,
             "team_id": str(team_id) if team_id else None, "reason": reason, "basis": basis,
             "override": details.get("override", False)},
            actor_id=actor_id,
        )
        await session.flush()
        record_decision(
            session, tournament_id, "award_confirmed", reason,
            {"award_code": award.award_code, "player_id": award.player_id, "team_id": award.team_id,
             "selection_method": award.selection_method, "evidence": award.evidence, "confirmed_at": award.confirmed_at},
            subject_id=award.id, actor_id=actor_id,
        )
        await session.flush()
        return award


async def confirm_player_of_match(
    session: AsyncSession,
    tournament_id: UUID,
    match_id: UUID,
    player_id: UUID,
    reason: str,
    *,
    actor_id: str | None = None,
) -> TournamentAward:
    async with tournament_transaction(session, "Player of the Match"):
        match = await session.scalar(
            select(Match)
            .join(Fixture, Fixture.match_id == Match.id)
            .join(FixtureGenerationRun, FixtureGenerationRun.id == Fixture.generation_run_id)
            .where(
                Match.id == match_id,
                Match.tournament_id == tournament_id,
                FixtureGenerationRun.status == "published",
            )
        )
        if match is None or match.status != MatchStatus.COMPLETED:
            raise ValidationError("Player of the Match requires an official completed tournament match")

        played = await session.scalar(
            select(MatchPlayer.id).where(MatchPlayer.match_id == match_id, MatchPlayer.player_id == player_id)
        )
        if played is None:
            raise ValidationError("Player did not play in this match")

        return await confirm_award(
            session, tournament_id, f"{PLAYER_OF_MATCH_PREFIX}{match_id}",
            player_id=player_id, reason=reason, match_id=match_id, actor_id=actor_id,
        )


async def revoke_award(
    session: AsyncSession,
    tournament_id: UUID,
    award_code: str,
    reason: str,
    *,
    actor_id: str | None = None,
) -> TournamentAward:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("Revocation reason must be at least 10 characters")

    async with tournament_transaction(session, "Award revocation"):
        await _editable(session, tournament_id)
        award = await session.scalar(
            select(TournamentAward)
            .where(TournamentAward.tournament_id == tournament_id, TournamentAward.award_code == award_code.strip().lower())
            .with_for_update()
        )

        if award is None:
            raise NotFoundError("Award not found")
        if award.status != "confirmed":
            raise ConflictError("Award is not currently confirmed")

        award.status = "revoked"
        tournament_audit(
            session, tournament_id, "award_revoked",
            {"award_code": award.award_code, "reason": reason,
             "previous_player_id": str(award.player_id) if award.player_id else None,
             "previous_team_id": str(award.team_id) if award.team_id else None},
            actor_id=actor_id,
        )
        record_decision(
            session, tournament_id, "award_revoked", reason,
            {"award_code": award.award_code, "previous_player_id": award.player_id,
             "previous_team_id": award.team_id, "previous_evidence": award.evidence},
            subject_id=award.id, actor_id=actor_id,
        )
        await session.flush()
        return award


async def update_award_settings(
    session: AsyncSession,
    tournament_id: UUID,
    settings: AwardSettings,
    reason: str,
    *,
    actor_id: str | None = None,
) -> AwardSettings:
    async with tournament_transaction(session, "Award settings"):
        await _editable(session, tournament_id)
        record_decision(session, tournament_id, SETTINGS_DECISION, reason.strip(), settings.model_dump(mode="json"), actor_id=actor_id)
        tournament_audit(session, tournament_id, "award_settings_updated", {"reason": reason.strip()}, actor_id=actor_id)
        await session.flush()
        return settings


async def cast_award_vote(
    session: AsyncSession,
    tournament_id: UUID,
    award_code: str,
    *,
    voter: str,
    reason: str,
    player_id: UUID | None = None,
    team_id: UUID | None = None,
    score: int = 1,
    actor_id: str | None = None,
) -> dict:
    award_code = award_code.strip().lower()
    voter = voter.strip()

    async with tournament_transaction(session, "Award vote"):
        await _editable(session, tournament_id)
        settings = await get_award_settings(session, tournament_id)

        if not settings.voting_enabled:
            raise ConflictError("Committee voting is not enabled for this tournament")
        if settings.committee and voter not in settings.committee:
            raise ValidationError("Voter is not a member of the award committee")

        await _check_recipient(session, tournament_id, player_id, team_id)

        if award_code == "emerging_player" and player_id is not None:
            tournament = await session.get(Tournament, tournament_id)
            player = await session.get(Player, player_id)
            eligible, message = emerging_eligibility(
                player.date_of_birth if player else None, settings.emerging, tournament.start_date or date.today()
            )
            if not eligible:
                raise ValidationError(f"Player is not eligible for Emerging Player: {message}")

        payload = {"award_code": award_code, "voter": voter, "player_id": str(player_id) if player_id else None,
                   "team_id": str(team_id) if team_id else None, "score": score}
        record_decision(session, tournament_id, VOTE_DECISION, reason.strip(), payload, actor_id=actor_id)
        await session.flush()
        return await vote_tally(session, tournament_id, award_code)


async def publish_awards(session: AsyncSession, tournament_id: UUID, reason: str, *, actor_id: str | None = None) -> dict:
    async with tournament_transaction(session, "Award publication"):
        await _editable(session, tournament_id)
        awards = list(
            (
                await session.scalars(
                    select(TournamentAward).where(
                        TournamentAward.tournament_id == tournament_id, TournamentAward.status == "confirmed"
                    ).order_by(TournamentAward.award_code)
                )
            ).all()
        )
        if not awards:
            raise ConflictError("Confirm at least one award before publishing")

        snapshot = {"awards": [serialize_award(award) for award in awards]}
        record_decision(session, tournament_id, PUBLISHED, reason.strip(), snapshot, actor_id=actor_id)
        tournament_audit(session, tournament_id, "awards_published", {"count": len(awards), "reason": reason.strip()}, actor_id=actor_id)
        await session.flush()
        return {"published": True, "awards": snapshot["awards"]}


async def unpublish_awards(
    session: AsyncSession,
    tournament_id: UUID,
    reason: str,
    *,
    actor_id: str | None = None,
    allow_closed: bool = False,
) -> dict:
    async with tournament_transaction(session, "Award unpublication"):
        tournament = await locked_tournament(TournamentRepository(session), tournament_id)

        if tournament.status in CLOSED_STATUSES and not allow_closed:
            raise ConflictError("Reopen the tournament before unpublishing its awards")
        if not (await publication_state(session, tournament_id))["published"]:
            raise ConflictError("Awards are not published")

        record_decision(session, tournament_id, UNPUBLISHED, reason.strip(), {}, actor_id=actor_id)
        tournament_audit(session, tournament_id, "awards_unpublished", {"reason": reason.strip()}, actor_id=actor_id)
        await session.flush()
        return {"published": False}
