"""Stage 13 dispositions, corrections, champion determination and closeout."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from app.core.exceptions import ConflictError, ValidationError
from app.domain.tournament_rules import TournamentRules
from app.models import MatchStatus, TournamentStatus
from app.services import tournament_closeout as closeout
from app.services import tournament_results as results
from app.services.tournament_result_guard import guard_tournament_result_correction
from app.services.tournament_results import OfficialOutcome, PublishedFixture, validate_disposition


A, B = uuid4(), uuid4()


def fixture(**overrides):
    values = dict(id=uuid4(), tournament_id=uuid4(), generation_run_id=uuid4(), round_id=uuid4(), fixture_number=1,
                  home_team_id=A, away_team_id=B, match_id=None, status="published", version=1)
    values.update(overrides)
    return SimpleNamespace(**values)


# -------------------------------------------------------------------------
# Disposition policy
# -------------------------------------------------------------------------


def test_walkover_requires_permitted_forfeits_and_a_fixture_team():
    with pytest.raises(ConflictError):
        validate_disposition("walkover", A, fixture(), ["win", "tie"])
    with pytest.raises(ValidationError):
        validate_disposition("walkover", uuid4(), fixture(), ["win", "forfeit"])
    validate_disposition("walkover", A, fixture(), ["win", "forfeit"])


def test_no_result_requires_permitted_outcome_and_no_winner():
    with pytest.raises(ConflictError):
        validate_disposition("no_result", None, fixture(), ["win"])
    with pytest.raises(ValidationError):
        validate_disposition("abandoned", A, fixture(), ["win"])
    validate_disposition("no_result", None, fixture(), ["win", "no_result"])
    validate_disposition("abandoned", None, fixture(), ["win"])


def test_disposition_needs_both_teams():
    with pytest.raises(ConflictError):
        validate_disposition("abandoned", None, fixture(away_team_id=None), ["win"])


def test_knockout_advancement_only_for_tied_or_abandoned_knockout_matches():
    tied = SimpleNamespace(status=MatchStatus.COMPLETED, result_type="tie", winner_team_id=None, result_margin=0, team_a_id=A, team_b_id=B)
    won = SimpleNamespace(status=MatchStatus.COMPLETED, result_type="runs", winner_team_id=A, result_margin=4, team_a_id=A, team_b_id=B)
    with pytest.raises(ConflictError):
        validate_disposition("knockout_advancement", A, fixture(), ["win"], stage="league", match=tied)
    with pytest.raises(ConflictError):
        validate_disposition("knockout_advancement", A, fixture(), ["win"], stage="knockout", match=won)
    with pytest.raises(ValidationError):
        validate_disposition("knockout_advancement", uuid4(), fixture(), ["win"], stage="knockout", match=tied)
    validate_disposition("knockout_advancement", A, fixture(), ["win"], stage="knockout", match=tied)


def disposition_session(match=None):
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=True)
    session.scalar = AsyncMock(return_value="league")
    session.get = AsyncMock(return_value=match)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def disposition_patches(target, existing):
    rules = TournamentRules.model_validate({"allowed_outcomes": ["win", "tie", "forfeit", "no_result"]})
    return [
        patch.object(results, "locked_tournament", AsyncMock(return_value=SimpleNamespace(status=TournamentStatus.LIVE))),
        patch.object(results, "_lock_fixture", AsyncMock(return_value=target)),
        patch("app.services.tournament_standings.get_standings_rules", AsyncMock(return_value=(None, rules))),
        patch.object(results, "current_dispositions", AsyncMock(side_effect=lambda *_: dict(existing))),
        patch.object(results, "_refresh_bracket", AsyncMock(return_value={"changed_count": 0})),
    ]


async def test_disposition_marks_fixture_and_refreshes_bracket_atomically():
    target = fixture()
    session = disposition_session()
    stack = disposition_patches(target, {})
    for item in stack:
        item.start()
    try:
        result = await results.record_fixture_disposition(
            session, target.tournament_id, target.id, outcome="walkover", winner_team_id=A, reason="Opponent failed to arrive",
        )
    finally:
        for item in stack:
            item.stop()
    assert result["fixture_status"] == "completed" and target.version == 2
    assert result["bracket"] == {"changed_count": 0}
    added = [call.args[0] for call in session.add.call_args_list]
    assert any(type(item).__name__ == "FixtureChangeAudit" for item in added)
    assert any(type(item).__name__ == "TournamentDecision" for item in added)


async def test_concurrent_duplicate_disposition_is_rejected():
    """The tournament row lock serializes writers; the loser sees the winner's decision."""

    target = fixture()
    recorded = {}
    lock = asyncio.Lock()

    async def locked(*_):
        await lock.acquire()
        return SimpleNamespace(status=TournamentStatus.LIVE)

    def remember(session, tournament_id, decision_type, reason, payload, **kwargs):
        recorded[target.id] = payload
        lock.release()
        return SimpleNamespace(id=uuid4())

    stack = disposition_patches(target, recorded)
    stack[0] = patch.object(results, "locked_tournament", locked)
    stack.append(patch.object(results, "record_decision", remember))
    for item in stack:
        item.start()
    try:
        outcomes = await asyncio.gather(
            results.record_fixture_disposition(disposition_session(), target.tournament_id, target.id,
                                               outcome="no_result", reason="Rain, no play possible"),
            results.record_fixture_disposition(disposition_session(), target.tournament_id, target.id,
                                               outcome="walkover", winner_team_id=B, reason="Late duplicate submission"),
            return_exceptions=True,
        )
    finally:
        for item in stack:
            item.stop()
        if lock.locked():
            lock.release()
    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert sum(isinstance(item, ConflictError) for item in outcomes) == 1


async def test_started_match_keeps_its_scored_result():
    target = fixture(match_id=uuid4())
    live = SimpleNamespace(status=MatchStatus.LIVE)
    stack = disposition_patches(target, {})
    for item in stack:
        item.start()
    try:
        with pytest.raises(ConflictError, match="scored result"):
            await results.record_fixture_disposition(
                disposition_session(live), target.tournament_id, target.id, outcome="abandoned", reason="Rain stopped play early",
            )
    finally:
        for item in stack:
            item.stop()


# -------------------------------------------------------------------------
# Corrections after official results
# -------------------------------------------------------------------------


def guard_session(match, tournament, downstream=(), protected=None):
    session = MagicMock()

    async def get(model, _id):
        return match if model.__name__ == "Match" else tournament

    session.get = AsyncMock(side_effect=get)
    executed = MagicMock()
    executed.all.return_value = list(downstream)
    session.execute = AsyncMock(return_value=executed)
    session.scalar = AsyncMock(return_value=protected)
    return session


async def test_correction_blocked_after_tournament_completion():
    match = SimpleNamespace(tournament_id=uuid4(), status=MatchStatus.COMPLETED)
    session = guard_session(match, SimpleNamespace(status=TournamentStatus.COMPLETED))
    with pytest.raises(ConflictError, match="Reopen"):
        await guard_tournament_result_correction(session, uuid4())


async def test_correction_blocked_when_downstream_bracket_match_started():
    match = SimpleNamespace(tournament_id=uuid4(), status=MatchStatus.COMPLETED)
    session = guard_session(match, SimpleNamespace(status=TournamentStatus.LIVE), downstream=[(uuid4(), uuid4())], protected=uuid4())
    with pytest.raises(ConflictError, match="downstream"):
        await guard_tournament_result_correction(session, uuid4())


async def test_correction_allowed_when_nothing_depends_on_result():
    match = SimpleNamespace(tournament_id=uuid4(), status=MatchStatus.COMPLETED)
    session = guard_session(match, SimpleNamespace(status=TournamentStatus.LIVE))
    await guard_tournament_result_correction(session, uuid4())


# -------------------------------------------------------------------------
# Champion and closeout
# -------------------------------------------------------------------------


def table(rows, pending=()):
    return {"pending_fixtures": list(pending), "disputed_fixtures": [], "ruleset_version": 1, "warnings": [],
            "ranking_unresolved": any(row["ranking_unresolved"] for row in rows),
            "tables": [{"group_name": "League", "standings": rows}]}


async def test_league_champion_requires_resolved_first_place():
    rules = TournamentRules()
    leader = {"team_id": A, "ranking_unresolved": False, "adjudicated": False}
    second = {"team_id": B, "ranking_unresolved": False}
    with patch.object(closeout, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(closeout, "calculate_tournament_standings", AsyncMock(return_value=table([leader, second]))):
        champion = await closeout.determine_champion(MagicMock(), uuid4())
    assert champion["champion_team_id"] == A and champion["runner_up_team_id"] == B

    tied = [{**leader, "ranking_unresolved": True}, {**second, "ranking_unresolved": True}]
    with patch.object(closeout, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(closeout, "calculate_tournament_standings", AsyncMock(return_value=table(tied))):
        with pytest.raises(ConflictError, match="tied"):
            await closeout.determine_champion(MagicMock(), uuid4())


def knockout_fixture(round_number, home=A, away=B):
    return PublishedFixture(fixture=fixture(home_team_id=home, away_team_id=away), stage="knockout",
                            round_number=round_number, group_name=None, review_message=None)


async def test_best_of_three_final_needs_a_majority():
    rules = TournamentRules.model_validate({"structure": "knockout", "best_of_finals": 3})
    finals = [knockout_fixture(3), knockout_fixture(3), knockout_fixture(3)]
    semi = knockout_fixture(2, home=A, away=uuid4())
    outcomes = {
        finals[0].fixture.id: OfficialOutcome("win", A, B),
        finals[1].fixture.id: OfficialOutcome("win", B, A),
        finals[2].fixture.id: OfficialOutcome("win", A, B),
        semi.fixture.id: OfficialOutcome("win", A, semi.fixture.away_team_id),
    }
    with patch.object(closeout, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(closeout, "published_fixtures", AsyncMock(return_value=[semi, *finals])), \
         patch.object(closeout, "fixture_outcomes", AsyncMock(return_value=(outcomes, {}))):
        champion = await closeout.determine_champion(MagicMock(), uuid4())
    assert champion["champion_team_id"] == A and champion["runner_up_team_id"] == B
    assert champion["method"] == "best_of_3_final"


async def test_tied_final_without_adjudication_has_no_champion():
    rules = TournamentRules.model_validate({"structure": "knockout"})
    final = knockout_fixture(1)
    outcomes = {final.fixture.id: OfficialOutcome("tie")}
    with patch.object(closeout, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(closeout, "published_fixtures", AsyncMock(return_value=[final])), \
         patch.object(closeout, "fixture_outcomes", AsyncMock(return_value=(outcomes, {}))):
        with pytest.raises(ConflictError, match="adjudication"):
            await closeout.determine_champion(MagicMock(), uuid4())

    outcomes = {final.fixture.id: OfficialOutcome("tie", adjudicated_team_id=B)}
    with patch.object(closeout, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(closeout, "published_fixtures", AsyncMock(return_value=[final])), \
         patch.object(closeout, "fixture_outcomes", AsyncMock(return_value=(outcomes, {}))):
        assert (await closeout.determine_champion(MagicMock(), uuid4()))["champion_team_id"] == B


async def test_readiness_reports_every_blocker():
    pending = PublishedFixture(fixture=fixture(status="postponed"), stage="league", round_number=1, group_name=None, review_message=None)
    reviewed = PublishedFixture(fixture=fixture(fixture_number=2), stage="league", round_number=1, group_name=None,
                                review_message="A prerequisite result changed")
    outcomes = {pending.fixture.id: OfficialOutcome("pending"), reviewed.fixture.id: OfficialOutcome("win", A, B)}
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(status=TournamentStatus.LIVE))
    with patch.object(closeout, "published_fixtures", AsyncMock(return_value=[pending, reviewed])), \
         patch.object(closeout, "fixture_outcomes", AsyncMock(return_value=(outcomes, {}))), \
         patch.object(closeout, "_bracket_checks", AsyncMock(return_value=[])), \
         patch.object(closeout, "calculate_tournament_standings", AsyncMock(return_value=table([]))), \
         patch.object(closeout, "determine_champion", AsyncMock(side_effect=ConflictError("League fixtures are unfinished"))), \
         patch.object(closeout, "publication_state", AsyncMock(return_value={"published": False})):
        readiness = await closeout.closeout_readiness(session, uuid4())

    assert not readiness["ready_to_finalize"]
    text = " | ".join(readiness["blockers"])
    assert "postponed" in text and "prerequisite" in text and "Champion" in text and "Awards" in text
    assert readiness["checks"]["fixtures"] == {"total": 2, "final": 1, "pending": 1, "disputed": 0}
    assert readiness["reopening_policy"]


async def test_finalize_refuses_while_blockers_remain():
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=True)
    with patch.object(closeout, "locked_tournament", AsyncMock(return_value=SimpleNamespace(status=TournamentStatus.LIVE))), \
         patch.object(closeout, "closeout_readiness", AsyncMock(return_value={"blockers": ["Fixture 3 is postponed"], "warnings": []})):
        with pytest.raises(ConflictError, match="postponed"):
            await closeout.finalize_tournament(session, uuid4())


@pytest.mark.parametrize("status", [TournamentStatus.ARCHIVED, TournamentStatus.LIVE])
async def test_only_completed_tournaments_can_be_reopened(status):
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=True)
    with patch.object(closeout, "locked_tournament", AsyncMock(return_value=SimpleNamespace(status=status))):
        with pytest.raises(ConflictError, match="Only completed"):
            await closeout.reopen_tournament(session, uuid4(), "Scoring error found in the final")


async def test_reopen_requires_a_reason():
    with pytest.raises(ValidationError):
        await closeout.reopen_tournament(MagicMock(), uuid4(), "short")
