"""Stage 13 points table: NRR, all-outs, special results, ties, adjudication."""

import random
from fractions import Fraction
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.domain.tournament_rules import TournamentRules
from app.models import MatchStatus
from app.services.tournament_results import OfficialOutcome, resolve_outcome
from app.services.tournament_standings import (
    adjudication_signature,
    compute_standings,
    overs_notation,
)


A, B, C, D = (uuid4() for _ in range(4))
NAMES = {A: "Alpha", B: "Bravo", C: "Charlie", D: "Delta"}


def teams(*ids, group="league"):
    return [{"team_id": team, "team_name": NAMES[team], "group_key": group, "group_name": "League"} for team in ids]


def innings(batting, bowling, runs, wickets, balls, side=None):
    return {"batting_team_id": batting, "bowling_team_id": bowling, "total_runs": runs,
            "wickets": wickets, "legal_balls": balls, "batting_side_size": side}


def result(home, away, outcome, innings_list=(), total_overs=20, players=11):
    return {"fixture_id": uuid4(), "home_team_id": home, "away_team_id": away, "outcome": outcome,
            "innings": list(innings_list), "total_overs": total_overs, "balls_per_over": 6, "players_per_side": players}


def win(winner, loser):
    return OfficialOutcome("win", winner, loser, result_type="runs", result_margin=1)


def row(table, team):
    return next(item for item in table["tables"][0]["standings"] if item["team_id"] == team)


def test_nrr_uses_legal_ball_denominators_not_cricket_notation():
    # Alpha 50/1 in 5.0 overs; Bravo chase 51/2 in 4.3 overs (= 27 balls = 4.5 overs).
    table = compute_standings(
        teams=teams(A, B),
        results=[result(A, B, win(B, A), [innings(A, B, 50, 1, 30), innings(B, A, 51, 2, 27)], total_overs=5)],
        rules=TournamentRules(),
    )
    bravo, alpha = row(table, B), row(table, A)
    # 51 / 4.5 - 50 / 5 = 4/3 exactly; notation (51 / 4.3) would give a wrong value.
    assert bravo["net_run_rate_exact"] == "4/3"
    assert alpha["net_run_rate_exact"] == "-4/3"
    assert bravo["overs_faced"] == "4.3"
    assert bravo["overs_faced_decimal"] == pytest.approx(4.5)
    assert bravo["points"] == 2 and alpha["points"] == 0


def test_all_out_side_is_charged_full_quota_by_default():
    rows = [innings(A, B, 100, 10, 90), innings(B, A, 101, 3, 60)]
    table = compute_standings(teams=teams(A, B), results=[result(A, B, win(B, A), rows)], rules=TournamentRules())
    alpha = row(table, A)
    assert alpha["balls_faced"] == 120
    assert Fraction(alpha["net_run_rate_exact"]) == Fraction(100, 20) - Fraction(101, 10)


def test_all_out_overs_faced_policy_and_short_handed_side():
    rules = TournamentRules.model_validate({"standings_policy": {"all_out_net_run_rate_overs": "overs_faced"}})
    rows = [innings(A, B, 100, 10, 90), innings(B, A, 101, 3, 60)]
    table = compute_standings(teams=teams(A, B), results=[result(A, B, win(B, A), rows)], rules=rules)
    assert row(table, A)["balls_faced"] == 90

    # A side that started with 8 players is all out at 7 wickets.
    rows = [innings(A, B, 60, 7, 50, side=8), innings(B, A, 61, 1, 40)]
    table = compute_standings(teams=teams(A, B), results=[result(A, B, win(B, A), rows)], rules=TournamentRules())
    assert row(table, A)["balls_faced"] == 120


def test_match_without_fixed_quota_uses_overs_faced_for_all_out():
    rows = [innings(A, B, 80, 10, 70), innings(B, A, 81, 2, 50)]
    table = compute_standings(teams=teams(A, B), results=[result(A, B, win(B, A), rows, total_overs=None)], rules=TournamentRules())
    assert row(table, A)["balls_faced"] == 70


def test_abandoned_and_no_result_share_points_and_never_touch_nrr():
    table = compute_standings(
        teams=teams(A, B, C),
        results=[
            result(A, B, OfficialOutcome("abandoned"), [innings(A, B, 99, 1, 60)]),
            result(A, C, OfficialOutcome("no_result")),
        ],
        rules=TournamentRules(),
    )
    alpha = row(table, A)
    assert alpha["abandoned"] == 1 and alpha["no_result"] == 1
    assert alpha["points"] == 2
    assert alpha["runs_for"] == 0 and alpha["net_run_rate"] == 0

    rules = TournamentRules.model_validate({"standings_policy": {"abandoned_match_points": "none"}})
    table = compute_standings(teams=teams(A, B), results=[result(A, B, OfficialOutcome("abandoned"))], rules=rules)
    assert row(table, A)["points"] == 0 and row(table, A)["played"] == 1


def test_walkover_awards_points_without_nrr():
    outcome = OfficialOutcome("forfeit", A, B, "disposition")
    table = compute_standings(teams=teams(A, B), results=[result(A, B, outcome)], rules=TournamentRules())
    alpha, bravo = row(table, A), row(table, B)
    assert alpha["points"] == 2 and alpha["won"] == 1 and alpha["walkover_wins"] == 1
    assert bravo["forfeited"] == 1 and bravo["lost"] == 1 and bravo["points"] == 0
    assert alpha["balls_bowled"] == 0 and alpha["net_run_rate"] == 0


def test_walkover_full_overs_credit_policy():
    rules = TournamentRules.model_validate({"standings_policy": {"forfeit_net_run_rate": "winner_credited_full_overs"}})
    table = compute_standings(teams=teams(A, B), results=[result(A, B, OfficialOutcome("forfeit", A, B))], rules=rules)
    assert row(table, A)["balls_bowled"] == 120
    assert row(table, B)["balls_faced"] == 0


def test_cancelled_fixture_is_excluded_entirely():
    table = compute_standings(teams=teams(A, B), results=[result(A, B, OfficialOutcome("excluded"))], rules=TournamentRules())
    assert row(table, A)["played"] == 0


def test_pending_and_disputed_results_never_count():
    pending = result(A, B, OfficialOutcome("pending"))
    disputed = result(A, B, OfficialOutcome("disputed"))
    table = compute_standings(teams=teams(A, B), results=[pending, disputed], rules=TournamentRules())
    assert table["pending_fixtures"] == [str(pending["fixture_id"])]
    assert table["disputed_fixtures"] == [str(disputed["fixture_id"])]
    assert row(table, A)["played"] == 0


def test_tied_points_are_separated_by_wins_then_nrr():
    results = [
        result(A, C, win(A, C), [innings(A, C, 200, 2, 120), innings(C, A, 100, 9, 120)]),
        result(B, D, win(B, D), [innings(B, D, 150, 2, 120), innings(D, B, 140, 9, 120)]),
    ]
    table = compute_standings(teams=teams(A, B, C, D), results=results, rules=TournamentRules())
    ranked = table["tables"][0]["standings"]
    assert [item["team_id"] for item in ranked[:2]] == [A, B]
    assert ranked[0]["rank"] == 1 and ranked[1]["rank"] == 2
    assert not table["ranking_unresolved"]


def test_identical_rows_stay_unresolved_until_adjudicated():
    results = [
        result(A, C, win(A, C), [innings(A, C, 150, 2, 120), innings(C, A, 100, 9, 120)]),
        result(B, D, win(B, D), [innings(B, D, 150, 2, 120), innings(D, B, 100, 9, 120)]),
    ]
    table = compute_standings(teams=teams(A, B, C, D), results=results, rules=TournamentRules())
    top = table["tables"][0]["standings"][:2]
    assert {item["rank"] for item in top} == {1}
    assert all(item["ranking_unresolved"] for item in top)
    assert table["ranking_unresolved"]

    signature_rows = [{**item, "net_run_rate": Fraction(item["net_run_rate_exact"])} for item in top]
    adjudication = {"team_ids": [str(B), str(A)], "signature": adjudication_signature(signature_rows),
                    "reason": "Drawing of lots by the technical committee", "decision_id": "d1"}
    resolved = compute_standings(teams=teams(A, B, C, D), results=results, rules=TournamentRules(),
                                 adjudications={"league": adjudication})
    top = resolved["tables"][0]["standings"][:2]
    assert [item["team_id"] for item in top] == [B, A]
    assert [item["rank"] for item in top] == [1, 2]
    assert all(item["adjudicated"] for item in top)
    assert not any(item["ranking_unresolved"] for item in top)
    # Charlie and Delta are still genuinely tied and remain unresolved.
    assert resolved["ranking_unresolved"]


def test_stale_adjudication_is_ignored_when_results_change():
    adjudication = {"team_ids": [str(B), str(A)], "signature": [["stale"]], "reason": "old", "decision_id": "d1"}
    results = [
        result(A, C, win(A, C), [innings(A, C, 150, 2, 120), innings(C, A, 100, 9, 120)]),
        result(B, D, win(B, D), [innings(B, D, 150, 2, 120), innings(D, B, 100, 9, 120)]),
    ]
    table = compute_standings(teams=teams(A, B, C, D), results=results, rules=TournamentRules(),
                              adjudications={"league": adjudication})
    assert table["ranking_unresolved"]


def test_head_to_head_breaker_uses_only_matches_between_tied_teams():
    rules = TournamentRules.model_validate({"tie_breakers": ["points", "head_to_head", "net_run_rate"]})
    results = [
        result(A, B, win(B, A), [innings(A, B, 100, 9, 120), innings(B, A, 101, 9, 120)]),
        result(A, C, win(A, C), [innings(A, C, 300, 1, 120), innings(C, A, 50, 9, 120)]),
        result(B, D, win(D, B), [innings(B, D, 100, 9, 120), innings(D, B, 101, 9, 120)]),
        result(B, C, win(B, C), [innings(B, C, 101, 9, 120), innings(C, B, 100, 9, 120)]),
        result(A, D, win(A, D), [innings(A, D, 101, 9, 120), innings(D, A, 100, 9, 120)]),
    ]
    table = compute_standings(teams=teams(A, B, C, D), results=results, rules=rules)
    ranked = table["tables"][0]["standings"]
    # A and B both have 4 points; B beat A, so B ranks first despite A's better NRR.
    assert [item["team_id"] for item in ranked[:2]] == [B, A]


def test_points_always_rank_first_even_if_omitted_from_breakers():
    rules = TournamentRules.model_validate({"tie_breakers": ["net_run_rate"]})
    results = [result(A, B, win(B, A), [innings(A, B, 300, 0, 120), innings(B, A, 301, 9, 120)])]
    table = compute_standings(teams=teams(A, B), results=results, rules=rules)
    assert table["tables"][0]["standings"][0]["team_id"] == B
    assert table["tie_breakers"][0] == "points"


def test_deductions_and_bonuses_change_points_only():
    results = [result(A, B, win(A, B), [innings(A, B, 120, 3, 120), innings(B, A, 100, 9, 120)])]
    table = compute_standings(
        teams=teams(A, B), results=results, rules=TournamentRules(),
        adjustments=[{"team_id": A, "points": 1, "kind": "deduction"}, {"team_id": B, "points": 3, "kind": "bonus"}],
    )
    alpha, bravo = row(table, A), row(table, B)
    assert (alpha["points"], alpha["deductions"]) == (1, 1)
    assert (bravo["points"], bravo["bonus_points"]) == (3, 3)
    assert alpha["net_run_rate_exact"] == "1"
    assert table["tables"][0]["standings"][0]["team_id"] == B


def test_zero_denominators_give_zero_nrr_not_errors():
    table = compute_standings(teams=teams(A, B), results=[], rules=TournamentRules())
    alpha = row(table, A)
    assert alpha["net_run_rate"] == 0 and alpha["overs_faced"] == "0.0"
    assert overs_notation(27, 6) == "4.3" and overs_notation(13, 5) == "2.3"


def test_standings_are_deterministic_regardless_of_result_order():
    results = [
        result(A, B, win(A, B), [innings(A, B, 150, 3, 120), innings(B, A, 120, 8, 120)]),
        result(C, D, OfficialOutcome("tie"), [innings(C, D, 140, 6, 120), innings(D, C, 140, 9, 120)]),
        result(A, C, OfficialOutcome("no_result")),
        result(B, D, win(D, B), [innings(B, D, 90, 10, 100), innings(D, B, 91, 1, 50)]),
    ]
    baseline = compute_standings(teams=teams(A, B, C, D), results=results, rules=TournamentRules())
    for seed in range(5):
        shuffled = results[:]
        random.Random(seed).shuffle(shuffled)
        again = compute_standings(teams=teams(A, B, C, D), results=shuffled, rules=TournamentRules())
        strip = lambda table: [{k: v for k, v in item.items() if k != "form"} for item in table["tables"][0]["standings"]]
        assert strip(again) == strip(baseline)


def test_groups_are_ranked_separately():
    grouped = teams(A, B, group="g1") + [{**item, "group_key": "g2", "group_name": "B"} for item in teams(C, D)]
    grouped[0]["group_name"] = grouped[1]["group_name"] = "A"
    table = compute_standings(teams=grouped, results=[], rules=TournamentRules())
    assert [item["group_name"] for item in table["tables"]] == ["A", "B"]


# -------------------------------------------------------------------------
# Official result mapping
# -------------------------------------------------------------------------


def match(status, result_type=None, winner=None, margin=None):
    return SimpleNamespace(status=status, result_type=result_type, winner_team_id=winner, result_margin=margin,
                           team_a_id=A, team_b_id=B)


def test_scored_results_map_to_official_outcomes():
    assert resolve_outcome(A, B, match(MatchStatus.COMPLETED, "runs", A, 12)).outcome == "win"
    won = resolve_outcome(A, B, match(MatchStatus.COMPLETED, "wickets", B, 3))
    assert (won.winner_team_id, won.loser_team_id) == (B, A)
    assert resolve_outcome(A, B, match(MatchStatus.COMPLETED, "tie", None, 0)).outcome == "tie"
    assert resolve_outcome(A, B, match(MatchStatus.COMPLETED)).outcome == "disputed"
    assert resolve_outcome(A, B, match(MatchStatus.ABANDONED)).outcome == "abandoned"
    assert resolve_outcome(A, B, match(MatchStatus.LIVE)).outcome == "pending"
    assert resolve_outcome(A, B, None).outcome == "pending"


def test_dispositions_map_to_official_outcomes():
    walkover = resolve_outcome(A, B, None, {"outcome": "walkover", "winner_team_id": str(B)})
    assert walkover.outcome == "forfeit" and walkover.winner_team_id == B and walkover.loser_team_id == A
    assert resolve_outcome(A, B, None, {"outcome": "cancelled"}).outcome == "excluded"
    assert resolve_outcome(A, B, None, {"outcome": "no_result"}).outcome == "no_result"

    tied = match(MatchStatus.COMPLETED, "tie", None, 0)
    advanced = resolve_outcome(A, B, tied, {"outcome": "knockout_advancement", "winner_team_id": str(A)})
    assert advanced.outcome == "tie"  # scored result preserved
    assert advanced.advancing_team_id == A
    assert not advanced.has_winner
