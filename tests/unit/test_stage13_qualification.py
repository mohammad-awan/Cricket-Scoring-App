"""Stage 13 qualification scenarios and bracket-slot resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from app.models import MatchStatus
from app.services.tournament_qualification import SlotResolver, best_ranked, group_team_status


A, B, C, D = (uuid4() for _ in range(4))


def row(team, rank, points, unresolved=False, won=0, nrr="0"):
    return {"team_id": team, "rank": rank, "points": points, "won": won, "ranking_unresolved": unresolved,
            "net_run_rate_exact": nrr, "wickets_taken": 0, "team_name": str(team)}


def test_team_clinches_only_when_rivals_cannot_catch_up():
    rows = [row(A, 1, 8), row(B, 2, 4), row(C, 3, 2), row(D, 4, 0)]
    statuses = group_team_status(rows, {A: 1, B: 1, C: 1, D: 1}, top_k=2, win_points=2, complete=False)
    assert statuses[A] == "qualified"        # B can reach 6 and C 4: neither can match 8
    assert statuses[D] == "eliminated"       # A and B already above D's maximum of 2
    assert statuses[B] == "in_contention"
    assert statuses[C] == "in_contention"


def test_no_premature_promotion_when_points_can_still_be_matched():
    rows = [row(A, 1, 4), row(B, 2, 2), row(C, 3, 2), row(D, 4, 0)]
    statuses = group_team_status(rows, {A: 1, B: 2, C: 2, D: 2}, top_k=1, win_points=2, complete=False)
    assert statuses[A] == "in_contention"
    assert "qualified" not in statuses.values()


def test_completed_group_with_boundary_tie_awaits_adjudication():
    rows = [row(A, 1, 6), row(B, 2, 4, True), row(C, 2, 4, True), row(D, 4, 0)]
    statuses = group_team_status(rows, {}, top_k=2, win_points=2, complete=True)
    assert statuses[A] == "qualified"
    assert statuses[B] == statuses[C] == "awaiting_adjudication"
    assert statuses[D] == "eliminated"


def test_completed_group_tie_below_boundary_does_not_block():
    rows = [row(A, 1, 6), row(B, 2, 4), row(C, 3, 0, True), row(D, 3, 0, True)]
    statuses = group_team_status(rows, {}, top_k=2, win_points=2, complete=True)
    assert statuses[A] == statuses[B] == "qualified"
    assert statuses[C] == statuses[D] == "eliminated"


def group(name, rows, status="confirmed"):
    return {"group_name": name, "status": status, "standings": rows, "remaining_fixtures": 0 if status == "confirmed" else 1}


def test_best_runner_up_across_groups():
    groups = [
        group("A", [row(A, 1, 6), row(B, 2, 4, nrr="1/2")]),
        group("B", [row(C, 1, 6), row(D, 2, 4, nrr="1/4")]),
    ]
    best = best_ranked(groups, rank=2, count=1, breakers=["points", "head_to_head", "net_run_rate"])
    assert best["status"] == "confirmed"
    assert [item["team_id"] for item in best["qualifiers"]] == [B]
    assert "head_to_head" not in best["comparison_keys"]


def test_best_ranked_waits_for_groups_and_flags_boundary_ties():
    groups = [group("A", [row(A, 1, 6), row(B, 2, 4)]), group("B", [row(C, 1, 6), row(D, 2, 4)], status="awaiting_results")]
    assert best_ranked(groups, 2, 1, ["points"])["status"] == "awaiting_results"

    groups[1]["status"] = "confirmed"
    tied = best_ranked(groups, 2, 1, ["points", "net_run_rate"])
    assert tied["status"] == "awaiting_adjudication"
    assert tied["qualifiers"] == []


# -------------------------------------------------------------------------
# Bracket slot resolution
# -------------------------------------------------------------------------


def resolver_with(match=None, dispositions=None, groups=None):
    session = MagicMock()
    session.get = AsyncMock(return_value=match)
    resolver = SlotResolver(session, uuid4(), groups=groups)
    resolver._dispositions = dispositions or {}
    return resolver


def parent(number=1, match_id=None):
    return SimpleNamespace(id=uuid4(), fixture_number=number, match_id=match_id, home_team_id=A, away_team_id=B)


async def test_winner_and_loser_sources_follow_the_official_result():
    completed = SimpleNamespace(status=MatchStatus.COMPLETED, result_type="runs", winner_team_id=B, result_margin=5,
                                team_a_id=A, team_b_id=B)
    fixture = parent(match_id=uuid4())
    resolver = resolver_with(completed)
    assert (await resolver.resolve("winner:1", {1: fixture}))[0] == B
    assert (await resolver.resolve("loser:1", {1: fixture}))[0] == A


async def test_tie_blocks_advancement_until_adjudicated():
    tied = SimpleNamespace(status=MatchStatus.COMPLETED, result_type="tie", winner_team_id=None, result_margin=0,
                           team_a_id=A, team_b_id=B)
    fixture = parent(match_id=uuid4())
    team, message = await resolver_with(tied).resolve("winner:1", {1: fixture})
    assert team is None and "adjudication" in message

    abandoned = SimpleNamespace(status=MatchStatus.ABANDONED, result_type=None, winner_team_id=None, result_margin=None,
                                team_a_id=A, team_b_id=B)
    resolver = resolver_with(abandoned, {fixture.id: {"outcome": "knockout_advancement", "winner_team_id": str(A)}})
    assert (await resolver.resolve("winner:1", {1: fixture}))[0] == A
    assert (await resolver.resolve("loser:1", {1: fixture}))[0] == B


async def test_walkover_disposition_advances_without_a_scored_match():
    fixture = parent()
    resolver = resolver_with(None, {fixture.id: {"outcome": "walkover", "winner_team_id": str(B)}})
    assert (await resolver.resolve("winner:1", {1: fixture}))[0] == B


async def test_group_source_resolves_only_from_final_unambiguous_positions():
    final = {"group_name": "A", "remaining_fixtures": 0, "standings": [row(A, 1, 6), row(B, 2, 4, True), row(C, 2, 4, True)]}
    resolver = resolver_with(groups=[final])
    assert (await resolver.resolve("group:A:1", {}))[0] == A
    team, message = await resolver.resolve("group:A:2", {})
    assert team is None and "adjudicated" in message

    pending = {**final, "remaining_fixtures": 2}
    team, message = await resolver_with(groups=[pending]).resolve("group:A:1", {})
    assert team is None and "awaiting" in message

    assert (await resolver_with(groups=[final]).resolve("group:Z:1", {}))[0] is None
    assert (await resolver_with(groups=[final]).resolve("group:A:x", {}))[0] is None


async def test_qualification_report_marks_knockout_slots():
    from app.services import tournament_qualification as module

    standings = {
        "ruleset_id": uuid4(), "ruleset_version": 1, "ruleset_checksum": "x", "pending_fixtures": [], "disputed_fixtures": [],
        "tie_breakers": ["points", "net_run_rate"],
        "tables": [{"group_key": "planner:A", "group_id": None, "group_name": "A",
                    "standings": [row(A, 1, 4), row(B, 2, 0)]}],
    }
    slot = SimpleNamespace(fixture=SimpleNamespace(id=uuid4(), fixture_number=3, home_team_id=None, away_team_id=None),
                           stage="knockout", home_source="group:A:1", away_source="group:A:2")
    rules = SimpleNamespace(points=SimpleNamespace(win=2))
    with patch.object(module, "calculate_tournament_standings", AsyncMock(return_value=standings)), \
         patch.object(module, "get_standings_rules", AsyncMock(return_value=(None, rules))), \
         patch.object(module, "published_fixtures", AsyncMock(return_value=[slot])):
        report = await module.tournament_qualification(MagicMock(), uuid4(), 1)

    assert report["groups"][0]["status"] == "confirmed"
    assert report["advancement_permitted"]
    resolved = {item["side"]: item["resolved_team_id"] for item in report["knockout_slots"]}
    assert resolved == {"home": A, "away": B}


@pytest.mark.parametrize("source", ["winner:9", "mystery:1"])
async def test_unknown_sources_never_resolve(source):
    assert (await resolver_with().resolve(source, {}))[0] is None
