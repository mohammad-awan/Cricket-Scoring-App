from types import SimpleNamespace
from uuid import uuid4
from app.repositories.scorecard import DeliveryScoreRow, MatchPlayerRow
from app.services.scorecard import (
    batting_scorecard,
    bowling_scorecard,
    extras_summary,
    innings_totals,
    partnership_scorecard,
    required_run_rate,
)
from app.services.scoring import ChaseState
from app.services.scoring.chase import finalize_match_result


def delivery(
    *,
    number: int,
    striker_id,
    striker_name: str,
    non_striker_id,
    non_striker_name: str,
    bowler_id,
    bowler_name: str,
    batter_runs: int = 0,
    wide_runs: int = 0,
    no_ball_runs: int = 0,
    bye_runs: int = 0,
    leg_bye_runs: int = 0,
    is_legal_ball: bool = True,
    wicket_type: (
        str | None
    ) = None,
    dismissed_player_id=None,
    dismissed_player_name: (
        str | None
    ) = None,
    fielder_id=None,
    fielder_name: (
        str | None
    ) = None,
    next_batter_id=None,
) -> DeliveryScoreRow:

    extra_runs = (
        wide_runs
        + no_ball_runs
        + bye_runs
        + leg_bye_runs
    )

    return DeliveryScoreRow(
        id=uuid4(),

        delivery_number=number,
        over_number=1,
        ball_number=max(number, 1),
        striker_id=striker_id,
        striker_name=striker_name,
        striker_short_name=None,
        non_striker_id=non_striker_id,
        non_striker_name=non_striker_name,
        non_striker_short_name=None,
        bowler_id=bowler_id,
        bowler_name=bowler_name,
        bowler_short_name=None,
        batter_runs=batter_runs,
        wide_runs=wide_runs,
        no_ball_runs=no_ball_runs,
        bye_runs=bye_runs,
        leg_bye_runs=leg_bye_runs,
        total_runs=batter_runs + extra_runs,
        is_legal_ball=is_legal_ball,
        wicket_type=wicket_type,
        dismissed_player_id=dismissed_player_id,
        dismissed_player_name=dismissed_player_name,
        dismissed_player_short_name=None,
        fielder_id=fielder_id,
        fielder_name=fielder_name,
        fielder_short_name=None,
        next_batter_id=next_batter_id,
    )


def test_batting_bowling_extras_and_totals() -> None:
    batter_a = uuid4()
    batter_b = uuid4()
    bowler = uuid4()
    fielder = uuid4()


    deliveries = [
        delivery(
            number=1,
            striker_id=batter_a,
            striker_name="Batter A",
            non_striker_id=batter_b,
            non_striker_name="Batter B",
            bowler_id=bowler,
            bowler_name="Bowler",
            batter_runs=4,
        ),

        delivery(
            number=2,
            striker_id=batter_a,
            striker_name="Batter A",
            non_striker_id=batter_b,
            non_striker_name="Batter B",
            bowler_id=bowler,
            bowler_name="Bowler",
            wide_runs=1,
            is_legal_ball=False,
        ),


        delivery(
            number=3,
            striker_id=batter_a,
            striker_name="Batter A",
            non_striker_id=batter_b,
            non_striker_name="Batter B",
            bowler_id=bowler,
            bowler_name="Bowler",
            batter_runs=1,
            wicket_type="run_out",
            dismissed_player_id=batter_b,
            dismissed_player_name="Batter B",
            fielder_id=fielder,
            fielder_name="Fielder",
        ),

    ]


    team_id = uuid4()


    players = [

        MatchPlayerRow(
            team_id=team_id,
            player_id=batter_a,
            full_name="Batter A",
            short_name=None,
            batting_order=1,
        ),


        MatchPlayerRow(
            team_id=team_id,
            player_id=batter_b,
            full_name="Batter B",
            short_name=None,
            batting_order=2,
        ),

    ]


    batting = batting_scorecard(players=players, deliveries=deliveries)
    bowling = bowling_scorecard(deliveries=deliveries, balls_per_over=6)
    extras = extras_summary(deliveries)
    totals = innings_totals(deliveries)
    assert batting[0].runs == 5
    assert batting[0].balls == 2
    assert batting[0].fours == 1
    assert batting[0].strike_rate == 250.0
    assert batting[1].dismissal == "run out (Fielder)"
    assert bowling[0].legal_balls == 2
    assert bowling[0].runs_conceded == 6
    assert bowling[0].wickets == 0
    assert bowling[0].wides == 1
    assert extras.total == 1
    assert totals.runs == 6
    assert totals.wickets == 1
    assert totals.legal_balls == 2


def test_required_run_rate() -> None:
    assert required_run_rate(60, 30, 6) == 12.0
    assert required_run_rate(0, 10, 6) == 0.0


def test_finalize_match_result_by_wickets() -> None:
    batting_team = uuid4()
    bowling_team = uuid4()


    match = SimpleNamespace(
        players_per_side=11,
        winner_team_id=None,
        result_type=None,
        result_margin=None,
        completed_at=None
    )

    innings = SimpleNamespace(
        batting_team_id=batting_team,
        bowling_team_id=bowling_team,
    )


    finalize_match_result(
        match,
        innings,
        wickets=4,
        chase=(
            ChaseState(
                target=151,
                batting_runs=151,
                bowling_runs=150,
            )
        ),
    )


    assert match.winner_team_id == batting_team
    assert match.result_type == "wickets"
    assert match.result_margin == 6
    assert match.completed_at is not None


def test_finalize_match_result_by_runs_and_tie() -> None:
    batting_team = uuid4()
    bowling_team = uuid4()


    match = SimpleNamespace(
        players_per_side=11,
        winner_team_id=None,
        result_type=None,
        result_margin=None,
        completed_at=None,
    )


    innings = SimpleNamespace(
        batting_team_id=batting_team,
        bowling_team_id=bowling_team,
    )


    finalize_match_result(
        match,
        innings,
        wickets=10,
        chase=(
            ChaseState(
                target=151,
                batting_runs=140,
                bowling_runs=150,
            )
        ),
    )


    assert match.winner_team_id == bowling_team
    assert match.result_type == "runs"
    assert match.result_margin == 10

    finalize_match_result(
        match,
        innings,
        wickets=10,
        chase=(
            ChaseState(
                target=151,
                batting_runs=150,
                bowling_runs=150,
            )
        ),
    )


    assert match.winner_team_id is None
    assert match.result_type == "tie"
    assert match.result_margin == 0