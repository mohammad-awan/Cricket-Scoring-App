"""Stage 13 player, team and record statistics from scored deliveries."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.models import RetirementType, WicketType
from app.services.tournament_statistics import (
    compute_partnerships,
    compute_player_profile,
    compute_player_statistics,
    compute_records,
    compute_team_statistics,
)


TEAM_A, TEAM_B, TEAM_C = uuid4(), uuid4(), uuid4()
TRANSFER, OPENER, PARTNER, BOWLER, KEEPER, SPINNER = (uuid4() for _ in range(6))
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def delivery(match, innings, number, striker, non_striker, bowler, *, runs=0, wide=0, no_ball=0, bye=0, leg_bye=0,
             wicket=None, dismissed=None, fielder=None, over=None):
    legal = not wide and not no_ball
    return {
        "match_id": match, "innings_id": innings, "delivery_number": number,
        "over_number": over if over is not None else (number - 1) // 6,
        "striker_id": striker, "non_striker_id": non_striker, "bowler_id": bowler, "batter_runs": runs,
        "wide_runs": wide, "no_ball_runs": no_ball, "bye_runs": bye, "leg_bye_runs": leg_bye,
        "total_runs": runs + wide + no_ball + bye + leg_bye, "is_legal_ball": legal,
        "wicket_type": wicket, "dismissed_player_id": dismissed, "fielder_id": fielder,
    }


def base_data():
    """Two matches: TRANSFER bats for TEAM_A in match 1 and TEAM_C in match 2."""

    m1, m2 = uuid4(), uuid4()
    i1, i2, i3 = uuid4(), uuid4(), uuid4()
    deliveries = [
        # Match 1, innings 1: TEAM_A bats, BOWLER (TEAM_B) bowls a maiden first over.
        *[delivery(m1, i1, n, TRANSFER, OPENER, BOWLER) for n in range(1, 7)],
        delivery(m1, i1, 7, TRANSFER, OPENER, SPINNER, runs=4, over=1),
        delivery(m1, i1, 8, TRANSFER, OPENER, SPINNER, wide=1, over=1),
        delivery(m1, i1, 9, TRANSFER, OPENER, SPINNER, no_ball=1, runs=6, over=1),
        delivery(m1, i1, 10, TRANSFER, OPENER, SPINNER, bye=2, over=1),
        delivery(m1, i1, 11, TRANSFER, OPENER, SPINNER, wicket=WicketType.CAUGHT, dismissed=TRANSFER, fielder=KEEPER, over=1),
        delivery(m1, i1, 12, PARTNER, OPENER, SPINNER, wicket=WicketType.RUN_OUT, dismissed=OPENER, fielder=None, over=1),
        # Match 1, innings 2: TEAM_B bats.
        delivery(m1, i2, 1, KEEPER, BOWLER, OPENER, runs=1),
        # Match 2: TRANSFER now plays for TEAM_C.
        delivery(m2, i3, 1, TRANSFER, PARTNER, BOWLER, runs=50),
        delivery(m2, i3, 2, TRANSFER, PARTNER, BOWLER, runs=1),
    ]
    return {
        "matches": [
            {"id": m1, "tournament_id": None, "team_a_id": TEAM_A, "team_b_id": TEAM_B, "balls_per_over": 6, "total_overs": 20,
             "players_per_side": 11, "winner_team_id": TEAM_A, "result_type": "runs", "result_margin": 18,
             "completed_at": NOW, "scheduled_at": NOW, "match_number": 1},
            {"id": m2, "tournament_id": None, "team_a_id": TEAM_C, "team_b_id": TEAM_B, "balls_per_over": 6, "total_overs": 20,
             "players_per_side": 11, "winner_team_id": TEAM_C, "result_type": "wickets", "result_margin": 9,
             "completed_at": NOW + timedelta(days=1), "scheduled_at": NOW, "match_number": 2},
        ],
        "innings": [
            {"id": uuid4(), "match_id": m2, "innings_number": 1, "batting_team_id": TEAM_B, "bowling_team_id": TEAM_C,
             "total_runs": 50, "wickets": 9, "legal_balls": 120, "batting_side_size": None},
            {"id": i1, "match_id": m1, "innings_number": 1, "batting_team_id": TEAM_A, "bowling_team_id": TEAM_B,
             "total_runs": 19, "wickets": 2, "legal_balls": 10, "batting_side_size": None},
            {"id": i2, "match_id": m1, "innings_number": 2, "batting_team_id": TEAM_B, "bowling_team_id": TEAM_A,
             "total_runs": 1, "wickets": 0, "legal_balls": 1, "batting_side_size": None},
            {"id": i3, "match_id": m2, "innings_number": 2, "batting_team_id": TEAM_C, "bowling_team_id": TEAM_B,
             "total_runs": 51, "wickets": 0, "legal_balls": 2, "batting_side_size": None},
        ],
        "deliveries": deliveries,
        "retirements": [],
        "match_players": [
            {"match_id": m1, "team_id": TEAM_A, "player_id": TRANSFER},
            {"match_id": m1, "team_id": TEAM_A, "player_id": OPENER},
            {"match_id": m1, "team_id": TEAM_A, "player_id": PARTNER},
            {"match_id": m1, "team_id": TEAM_B, "player_id": BOWLER},
            {"match_id": m1, "team_id": TEAM_B, "player_id": SPINNER},
            {"match_id": m1, "team_id": TEAM_B, "player_id": KEEPER},
            {"match_id": m2, "team_id": TEAM_C, "player_id": TRANSFER},
            {"match_id": m2, "team_id": TEAM_C, "player_id": PARTNER},
            {"match_id": m2, "team_id": TEAM_B, "player_id": BOWLER},
        ],
        "players": {pid: {"name": name, "date_of_birth": None} for pid, name in [
            (TRANSFER, "Transfer"), (OPENER, "Opener"), (PARTNER, "Partner"),
            (BOWLER, "Bowler"), (KEEPER, "Keeper"), (SPINNER, "Spinner")]},
        "teams": {TEAM_A: "Alpha", TEAM_B: "Bravo", TEAM_C: "Charlie"},
        "ids": {"m1": m1, "m2": m2, "i1": i1, "i3": i3},
    }


def find(rows, player):
    return next(row for row in rows if row["player_id"] == player)


def test_transferred_player_is_counted_once_with_both_teams():
    stats = compute_player_statistics(base_data())
    batter = find(stats["batting"], TRANSFER)
    assert batter["matches"] == 2
    assert [team["team_name"] for team in batter["teams"]] == ["Alpha", "Charlie"]
    assert batter["runs"] == 4 + 6 + 50 + 1
    assert sum(1 for row in stats["batting"] if row["player_id"] == TRANSFER) == 1


def test_team_filter_attributes_contributions_by_match_team():
    alpha = find(compute_player_statistics(base_data(), team_id=TEAM_A)["batting"], TRANSFER)
    charlie = find(compute_player_statistics(base_data(), team_id=TEAM_C)["batting"], TRANSFER)
    assert (alpha["runs"], alpha["matches"]) == (10, 1)
    assert (charlie["runs"], charlie["matches"]) == (51, 1)


def test_balls_faced_exclude_wides_and_include_no_balls():
    batter = find(compute_player_statistics(base_data(), team_id=TEAM_A)["batting"], TRANSFER)
    # 6 dots + 4 + no-ball + bye + wicket = 10 balls; the wide is excluded.
    assert batter["balls"] == 10
    assert batter["fours"] == 1 and batter["sixes"] == 1


def test_byes_are_not_charged_to_the_bowler_and_extras_are():
    spinner = find(compute_player_statistics(base_data())["bowling"], SPINNER)
    # 4 + wide 1 + (no-ball 1 + 6) = 12; byes excluded.
    assert spinner["runs_conceded"] == 12
    assert spinner["legal_balls"] == 4


def test_maiden_is_derived_from_complete_single_bowler_over():
    bowler = find(compute_player_statistics(base_data())["bowling"], BOWLER)
    spinner = find(compute_player_statistics(base_data())["bowling"], SPINNER)
    assert bowler["maidens"] == 1
    assert spinner["maidens"] == 0


def test_run_out_is_a_dismissal_but_not_a_bowler_wicket():
    stats = compute_player_statistics(base_data())
    spinner = find(stats["bowling"], SPINNER)
    assert spinner["wickets"] == 1  # caught only
    summary = stats["dismissal_summary"]
    assert summary["total_dismissals"] == 2
    assert summary["credited_to_bowler"] == 1
    assert summary["run_outs"] == 1
    assert summary["fielder_not_recorded"] == 1
    keeper = find(stats["fielding"], KEEPER)
    assert keeper["catches"] == 1 and keeper["total_dismissals"] == 1
    assert find(stats["batting"], OPENER)["dismissals"] == 1


def test_zero_denominators_return_none_not_infinity_or_zero():
    stats = compute_player_statistics(base_data())
    transfer = find(stats["batting"], TRANSFER)
    partner = find(stats["batting"], PARTNER)
    opener = find(stats["batting"], OPENER)
    assert partner["average"] is None  # never dismissed
    assert opener["strike_rate"] is None and opener["balls"] == 0  # run out without facing
    assert opener["average"] == 0.0
    assert transfer["average"] == 61.0
    data = base_data()
    data["deliveries"] = [delivery(data["ids"]["m1"], data["ids"]["i1"], 1, TRANSFER, OPENER, BOWLER, wide=1)]
    only_wides = find(compute_player_statistics(data)["bowling"], BOWLER)
    assert only_wides["economy"] is None and only_wides["average"] is None and only_wides["strike_rate"] is None


def test_highest_score_not_out_marker_and_recent_form():
    batter = find(compute_player_statistics(base_data())["batting"], TRANSFER)
    assert batter["highest_score_display"] == "51*"
    assert batter["recent_form"] == ["10", "51*"]
    assert batter["fifties"] == 1 and batter["not_outs"] == 1


def test_retired_out_counts_as_dismissal_but_retired_hurt_does_not():
    data = base_data()
    data["retirements"] = [{"match_id": data["ids"]["m2"], "innings_id": data["ids"]["i3"], "player_id": PARTNER,
                            "retirement_type": RetirementType.OUT}]
    stats = compute_player_statistics(data)
    assert find(stats["batting"], PARTNER)["dismissals"] == 1
    assert stats["dismissal_summary"]["retired_out"] == 1

    data["retirements"][0]["retirement_type"] = RetirementType.HURT
    assert find(compute_player_statistics(data)["batting"], PARTNER)["dismissals"] == 0


def test_leaderboard_qualification_and_deterministic_order():
    stats = compute_player_statistics(base_data(), min_innings=2, min_balls=6)
    assert stats["batting"][0]["player_id"] == TRANSFER
    assert find(stats["batting"], TRANSFER)["qualifies"]
    assert not find(stats["batting"], OPENER)["qualifies"]
    assert find(stats["bowling"], BOWLER)["qualifies"]
    assert stats["bowling"] == compute_player_statistics(base_data(), min_innings=2, min_balls=6)["bowling"]


def test_partnerships_split_on_wickets_and_pair_changes():
    rows = compute_partnerships(base_data())
    first = [row for row in rows if row["wicket"] == 1 and row["team_name"] == "Alpha"][0]
    assert first["runs"] == 4 + 1 + 7 + 2
    assert {p["player_name"] for p in first["players"]} == {"Transfer", "Opener"}
    assert rows[0]["runs"] == 51


def test_team_statistics_and_form():
    teams = {row["team_id"]: row for row in compute_team_statistics(base_data())}
    assert teams[TEAM_B]["lost"] == 2 and teams[TEAM_B]["matches"] == 2
    assert [item["result"] for item in teams[TEAM_B]["form"]] == ["L", "L"]
    assert teams[TEAM_A]["highest_total"] == 19
    assert teams[TEAM_B]["wides"] == 1 and teams[TEAM_B]["byes"] == 2


def test_records_include_chases_and_biggest_wins():
    records = compute_records(base_data())
    assert records["highest_totals"][0]["runs"] == 51
    assert records["biggest_wins_by_runs"][0]["margin_runs"] == 18
    assert records["biggest_wins_by_wickets"][0]["margin_wickets"] == 9
    assert records["successful_chases"][0]["target"] == 51
    assert records["successful_chases"][0]["balls_remaining"] == 118
    assert records["highest_individual_scores"][0]["display"] == "51* (2)"
    assert records["best_bowling_figures"][0]["player_id"] == SPINNER


def test_player_profile_lists_match_by_match_with_each_team():
    profile = compute_player_profile(base_data(), TRANSFER)
    assert [row["team_name"] for row in profile["matches"]] == ["Alpha", "Charlie"]
    assert profile["matches"][0]["batting"] == "10 (10)"
    assert profile["matches"][1]["batting"] == "51* (2)"
