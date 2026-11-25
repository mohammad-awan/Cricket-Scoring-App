"""Official tournament results.

Every Stage 13 calculation reads results through this module so that
standings, qualification, brackets, statistics and closeout agree on
what an "official" result is:

* A scored result comes only from a COMPLETED ``Match`` produced by the
  normal scoring engine (``result_type`` is ``runs``, ``wickets`` or
  ``tie``). There is no second tournament scoring engine.
* A fixture that was never (fully) played receives an organizer
  *disposition* - walkover, no result, abandoned or cancelled. A tied or
  abandoned knockout match may receive a ``knockout_advancement``
  disposition naming the advancing side (super over, bowl-out, higher
  seed, committee) without altering the scored result. A
  disposition is an immutable ``TournamentDecision`` with a reason, so
  the audit trail is preserved and the latest decision is authoritative.
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Match, MatchStatus, TournamentStatus
from app.models.entities.fixtures import (
    Fixture,
    FixtureBracketDependency,
    FixtureChangeAudit,
    FixtureGenerationRun,
    FixtureRound,
)
from app.repositories.tournaments import TournamentRepository
from app.services.tournament_decisions import (
    latest_by_key,
    list_decisions,
    record_decision,
)
from app.services.tournaments import (
    locked_tournament,
    tournament_audit,
    tournament_transaction,
)


DISPOSITION_SET = "fixture_disposition"
DISPOSITION_CLEAR = "fixture_disposition_revoked"
DISPOSITION_OUTCOMES = ("walkover", "no_result", "abandoned", "cancelled", "knockout_advancement")

# Outcomes that settle a fixture for standings, brackets and closeout.
FINAL_OUTCOMES = frozenset(
    {"win", "tie", "no_result", "abandoned", "forfeit", "excluded"}
)
STARTED_MATCH_STATUSES = frozenset(
    {MatchStatus.LIVE, MatchStatus.INNINGS_BREAK, MatchStatus.COMPLETED}
)
LEAGUE_STAGES = frozenset({"league", "group", "groups"})


@dataclass(frozen=True)
class OfficialOutcome:
    outcome: str
    winner_team_id: UUID | None = None
    loser_team_id: UUID | None = None
    source: str = "match"
    result_type: str | None = None
    result_margin: int | None = None
    disposition: dict | None = field(default=None, compare=False)
    adjudicated_team_id: UUID | None = None

    @property
    def is_final(self) -> bool:
        return self.outcome in FINAL_OUTCOMES

    @property
    def has_winner(self) -> bool:
        return self.outcome in {"win", "forfeit"} and self.winner_team_id is not None

    @property
    def advancing_team_id(self) -> UUID | None:
        """Team that progresses in a bracket from this fixture."""
        return self.winner_team_id if self.has_winner else self.adjudicated_team_id

    @property
    def counts_in_net_run_rate(self) -> bool:
        # Abandoned, no-result and walkover matches never contribute
        # runs or overs; forfeits are handled by explicit policy.
        return self.outcome in {"win", "tie"}


def resolve_outcome(
    home_team_id: UUID | None,
    away_team_id: UUID | None,
    match: Match | None,
    disposition: dict | None = None,
) -> OfficialOutcome:
    """Pure mapping from a fixture's match/disposition to its official outcome."""

    if disposition is not None:
        kind = disposition["outcome"]

        if kind == "knockout_advancement":
            base = resolve_outcome(home_team_id, away_team_id, match, None)
            return replace(
                base,
                adjudicated_team_id=UUID(str(disposition["winner_team_id"])),
                disposition=disposition,
            )

        if kind == "walkover":
            winner = UUID(str(disposition["winner_team_id"]))
            loser = away_team_id if winner == home_team_id else home_team_id
            return OfficialOutcome(
                "forfeit", winner, loser, "disposition", disposition=disposition
            )

        if kind == "cancelled":
            return OfficialOutcome("excluded", source="disposition", disposition=disposition)

        return OfficialOutcome(kind, source="disposition", disposition=disposition)

    if match is None:
        return OfficialOutcome("pending", source="none")

    if match.status == MatchStatus.ABANDONED:
        return OfficialOutcome("abandoned")

    if match.status != MatchStatus.COMPLETED:
        return OfficialOutcome("pending")

    teams = {match.team_a_id, match.team_b_id}
    result_type = getattr(match, "result_type", None)

    if result_type != "tie" and match.winner_team_id in teams:
        loser = (teams - {match.winner_team_id}).pop()
        return OfficialOutcome(
            "win",
            match.winner_team_id,
            loser,
            result_type=result_type,
            result_margin=getattr(match, "result_margin", None),
        )

    if result_type == "tie":
        return OfficialOutcome("tie", result_type="tie", result_margin=0)

    # Completed without a valid result: requires organizer review.
    return OfficialOutcome("disputed")


def result_text(outcome: OfficialOutcome, names: dict) -> str:
    def name(team_id):
        return names.get(team_id) or "Unknown team"

    if outcome.outcome == "win":
        unit = "run" if outcome.result_type == "runs" else "wicket"
        margin = outcome.result_margin or 0
        plural = "" if margin == 1 else "s"
        return f"{name(outcome.winner_team_id)} won by {margin} {unit}{plural}"

    return {
        "forfeit": f"{name(outcome.winner_team_id)} won by walkover",
        "tie": "Match tied",
        "no_result": "No result",
        "abandoned": "Match abandoned",
        "excluded": "Fixture cancelled",
        "disputed": "Result requires review",
    }.get(outcome.outcome, "Awaiting result")


@dataclass
class PublishedFixture:
    fixture: Fixture
    stage: str
    round_number: int
    group_name: str | None
    review_message: str | None
    home_source: str | None = None
    away_source: str | None = None


async def published_fixtures(
    session: AsyncSession,
    tournament_id: UUID,
    *,
    include_cancelled: bool = True,
) -> list[PublishedFixture]:
    """Fixtures of published generation runs with stage and planner group."""

    statement = (
        select(Fixture, FixtureRound.stage, FixtureRound.round_number, FixtureGenerationRun)
        .join(FixtureGenerationRun, FixtureGenerationRun.id == Fixture.generation_run_id)
        .join(FixtureRound, FixtureRound.id == Fixture.round_id)
        .where(
            Fixture.tournament_id == tournament_id,
            FixtureGenerationRun.status == "published",
        )
        .order_by(FixtureRound.round_number, Fixture.fixture_number)
    )

    if not include_cancelled:
        statement = statement.where(Fixture.status != "cancelled")

    rows = (await session.execute(statement)).all()
    result = []

    for fixture, stage, round_number, run in rows:
        configuration = run.configuration or {}
        metadata = {
            item.get("fixture_number"): item
            for item in configuration.get("snapshot", {}).get("fixtures", [])
        }
        meta = metadata.get(fixture.fixture_number, {})
        result.append(
            PublishedFixture(
                fixture=fixture,
                stage=meta.get("stage") or stage,
                round_number=round_number,
                group_name=meta.get("group"),
                review_message=configuration.get("reviews", {}).get(str(fixture.id)),
                home_source=meta.get("home_source"),
                away_source=meta.get("away_source"),
            )
        )

    return result


async def current_dispositions(
    session: AsyncSession,
    tournament_id: UUID,
) -> dict[UUID, dict]:
    decisions = await list_decisions(
        session, tournament_id, {DISPOSITION_SET, DISPOSITION_CLEAR}
    )
    latest = latest_by_key(decisions, lambda decision: decision.subject_id)

    return {
        fixture_id: {
            **decision.payload,
            "reason": decision.reason,
            "decision_id": str(decision.id),
            "recorded_at": decision.created_at.isoformat() if decision.created_at else None,
        }
        for fixture_id, decision in latest.items()
        if decision.decision_type == DISPOSITION_SET
    }


async def fixture_outcomes(
    session: AsyncSession,
    tournament_id: UUID,
    fixtures: list[PublishedFixture],
) -> tuple[dict[UUID, OfficialOutcome], dict[UUID, Match]]:
    match_ids = [item.fixture.match_id for item in fixtures if item.fixture.match_id]
    matches = (
        (await session.scalars(select(Match).where(Match.id.in_(match_ids)))).all()
        if match_ids
        else []
    )
    match_map = {match.id: match for match in matches}
    dispositions = await current_dispositions(session, tournament_id)

    outcomes = {}
    for item in fixtures:
        disposition = dispositions.get(item.fixture.id)
        match = match_map.get(item.fixture.match_id)

        if item.fixture.status == "cancelled" and disposition is None and (
            match is None or match.status != MatchStatus.COMPLETED
        ):
            # Cancelled through the Stage 12 fixture workflow (audited there).
            outcomes[item.fixture.id] = OfficialOutcome("excluded", source="fixture_cancelled")
            continue

        outcomes[item.fixture.id] = resolve_outcome(
            item.fixture.home_team_id, item.fixture.away_team_id, match, disposition
        )
    return outcomes, match_map


# ---------------------------------------------------------------------------
# Organizer dispositions
# ---------------------------------------------------------------------------


def validate_disposition(
    outcome: str,
    winner_team_id: UUID | None,
    fixture: Fixture,
    allowed_outcomes: list[str],
    *,
    stage: str = "league",
    match: Match | None = None,
) -> None:
    if outcome not in DISPOSITION_OUTCOMES:
        raise ValidationError("Unsupported fixture disposition")

    if fixture.home_team_id is None or fixture.away_team_id is None:
        raise ConflictError("Both fixture teams must be known before a disposition")

    if outcome == "knockout_advancement":
        if stage in LEAGUE_STAGES:
            raise ConflictError("Advancement adjudication applies only to knockout fixtures")
        base = resolve_outcome(fixture.home_team_id, fixture.away_team_id, match)
        if base.outcome not in {"tie", "abandoned", "no_result"}:
            raise ConflictError("Only a tied or abandoned knockout match needs an advancement adjudication")
        if winner_team_id not in {fixture.home_team_id, fixture.away_team_id}:
            raise ValidationError("The advancing team must be one of the fixture teams")
        return

    if outcome == "walkover":
        if "forfeit" not in allowed_outcomes:
            raise ConflictError("Competition rules do not permit forfeits/walkovers")

        if winner_team_id not in {fixture.home_team_id, fixture.away_team_id}:
            raise ValidationError("A walkover winner must be one of the fixture teams")

    elif winner_team_id is not None:
        raise ValidationError("Only walkovers name a winner")

    if outcome == "no_result" and "no_result" not in allowed_outcomes:
        raise ConflictError("Competition rules do not permit no-result outcomes")


async def _lock_fixture(session: AsyncSession, tournament_id: UUID, fixture_id: UUID) -> Fixture:
    fixture = await session.scalar(
        select(Fixture)
        .join(FixtureGenerationRun, FixtureGenerationRun.id == Fixture.generation_run_id)
        .where(
            Fixture.id == fixture_id,
            Fixture.tournament_id == tournament_id,
            FixtureGenerationRun.status == "published",
        )
        .with_for_update()
    )

    if fixture is None:
        raise NotFoundError("Published tournament fixture not found")

    return fixture


async def _ensure_downstream_unstarted(session: AsyncSession, fixture: Fixture) -> None:
    targets = (
        await session.scalars(
            select(Fixture.match_id)
            .join(FixtureBracketDependency, FixtureBracketDependency.fixture_id == Fixture.id)
            .where(FixtureBracketDependency.source_fixture_id == fixture.id)
        )
    ).all()
    target_ids = [match_id for match_id in targets if match_id is not None]

    if target_ids and await session.scalar(
        select(Match.id)
        .where(Match.id.in_(target_ids), Match.status.in_(list(STARTED_MATCH_STATUSES)))
        .limit(1)
    ):
        raise ConflictError("A downstream bracket match has already started from this result")


async def _refresh_bracket(session: AsyncSession, generation_run_id: UUID) -> dict:
    from app.services.fixture_planning import FixturePlanningService

    return await FixturePlanningService(session).progress(generation_run_id)


async def record_fixture_disposition(
    session: AsyncSession,
    tournament_id: UUID,
    fixture_id: UUID,
    *,
    outcome: str,
    reason: str,
    winner_team_id: UUID | None = None,
    actor_id: str | None = None,
) -> dict:
    from app.services.tournament_standings import get_standings_rules

    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A disposition reason of at least 10 characters is required")

    async with tournament_transaction(session, "Fixture disposition"):
        tournament = await locked_tournament(TournamentRepository(session), tournament_id)

        if tournament.status in {
            TournamentStatus.COMPLETED,
            TournamentStatus.ARCHIVED,
            TournamentStatus.CANCELLED,
        }:
            raise ConflictError("Reopen the tournament before changing fixture results")

        fixture = await _lock_fixture(session, tournament_id, fixture_id)
        _, rules = await get_standings_rules(session, tournament_id)
        stage = await session.scalar(select(FixtureRound.stage).where(FixtureRound.id == fixture.round_id))
        match = (
            await session.get(Match, fixture.match_id, with_for_update=True)
            if fixture.match_id is not None else None
        )
        validate_disposition(
            outcome, winner_team_id, fixture, list(rules.allowed_outcomes), stage=stage or "league", match=match
        )

        dispositions = await current_dispositions(session, tournament_id)

        if fixture.id in dispositions:
            raise ConflictError("Fixture already has a disposition. Revoke it with a reason first.")

        if outcome != "knockout_advancement" and match is not None and match.status in STARTED_MATCH_STATUSES:
            raise ConflictError(
                "A started or completed match keeps its scored result. "
                "Use scoring corrections instead of a disposition."
            )

        previous_status = fixture.status
        if outcome == "cancelled":
            fixture.status = "cancelled"
        elif outcome != "knockout_advancement":
            fixture.status = "completed"
        fixture.version += 1

        payload = {
            "fixture_id": fixture.id,
            "fixture_number": fixture.fixture_number,
            "outcome": outcome,
            "winner_team_id": winner_team_id,
            "match_id": fixture.match_id,
            "previous_fixture_status": previous_status,
        }
        session.add(
            FixtureChangeAudit(
                fixture_id=fixture.id,
                action=f"disposition_{outcome}",
                actor_id=actor_id,
                old_values={"status": previous_status},
                new_values={"status": fixture.status, "winner_team_id": str(winner_team_id) if winner_team_id else None},
                reason=reason,
            )
        )
        decision = record_decision(
            session, tournament_id, DISPOSITION_SET, reason, payload,
            subject_id=fixture.id, actor_id=actor_id,
        )
        tournament_audit(
            session, tournament_id, "fixture_disposition_recorded",
            {"fixture_id": str(fixture.id), "outcome": outcome, "reason": reason},
            actor_id=actor_id,
        )
        await session.flush()
        bracket = await _refresh_bracket(session, fixture.generation_run_id)

        return {
            "decision_id": decision.id,
            "fixture_id": fixture.id,
            "outcome": outcome,
            "winner_team_id": winner_team_id,
            "fixture_status": fixture.status,
            "fixture_version": fixture.version,
            "bracket": bracket,
        }


async def revoke_fixture_disposition(
    session: AsyncSession,
    tournament_id: UUID,
    fixture_id: UUID,
    *,
    reason: str,
    actor_id: str | None = None,
) -> dict:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A revocation reason of at least 10 characters is required")

    async with tournament_transaction(session, "Fixture disposition revocation"):
        tournament = await locked_tournament(TournamentRepository(session), tournament_id)

        if tournament.status in {TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED}:
            raise ConflictError("Reopen the tournament before changing fixture results")

        fixture = await _lock_fixture(session, tournament_id, fixture_id)
        dispositions = await current_dispositions(session, tournament_id)
        current = dispositions.get(fixture.id)

        if current is None:
            raise NotFoundError("Fixture has no active disposition")

        await _ensure_downstream_unstarted(session, fixture)

        previous_status = fixture.status
        fixture.status = current.get("previous_fixture_status") or "published"

        if fixture.status in {"completed", "cancelled"}:
            fixture.status = "published"

        fixture.version += 1
        session.add(
            FixtureChangeAudit(
                fixture_id=fixture.id,
                action="disposition_revoked",
                actor_id=actor_id,
                old_values={"status": previous_status, "outcome": current["outcome"]},
                new_values={"status": fixture.status},
                reason=reason,
            )
        )
        record_decision(
            session, tournament_id, DISPOSITION_CLEAR, reason,
            {"fixture_id": fixture.id, "previous": current},
            subject_id=fixture.id, actor_id=actor_id,
        )
        tournament_audit(
            session, tournament_id, "fixture_disposition_revoked",
            {"fixture_id": str(fixture.id), "reason": reason},
            actor_id=actor_id,
        )
        await session.flush()
        bracket = await _refresh_bracket(session, fixture.generation_run_id)

        return {
            "fixture_id": fixture.id,
            "fixture_status": fixture.status,
            "fixture_version": fixture.version,
            "bracket": bracket,
        }


__all__ = [
    "DISPOSITION_OUTCOMES",
    "FINAL_OUTCOMES",
    "LEAGUE_STAGES",
    "OfficialOutcome",
    "PublishedFixture",
    "current_dispositions",
    "fixture_outcomes",
    "published_fixtures",
    "record_fixture_disposition",
    "resolve_outcome",
    "result_text",
    "revoke_fixture_disposition",
]
