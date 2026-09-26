from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.schemas.scoring import DeliveryCreate
from app.services.scoring import (
    advance_batters,
    ball_position,
    bowler_change_required,
    chase_target,
    current_run_rate,
    max_innings,
    overs_display,
    previous_over_bowler_id,
    rebuild_from_deliveries,
    result_summary,
)


def test_only_stage4_runs_allowed() -> None:
    for runs in (0, 1, 2, 3, 4, 6):
        payload = DeliveryCreate(runs=runs)
        assert payload.runs == runs

    with pytest.raises(PydanticValidationError):
        DeliveryCreate(runs=5)


def test_ball_position() -> None:
    assert ball_position(0, 6) == (1, 1)
    assert ball_position(5, 6) == (1, 6)
    assert ball_position(6, 6) == (2, 1)


def test_custom_balls_per_over() -> None:
    assert ball_position(7, 8) == (1, 8)
    assert ball_position(8, 8) == (2, 1)


def test_odd_run_rotates_strike() -> None:
    striker = uuid4()
    non_striker = uuid4()

    result = advance_batters(
        striker,
        non_striker,
        runs=1,
        legal_balls_after=1,
        balls_per_over=6,
    )

    assert result == (non_striker, striker)


def test_even_run_keeps_strike() -> None:
    striker = uuid4()
    non_striker = uuid4()

    result = advance_batters(
        striker,
        non_striker,
        runs=4,
        legal_balls_after=3,
        balls_per_over=6,
    )

    assert result == (striker, non_striker)


def test_over_completion_changes_ends() -> None:
    striker = uuid4()
    non_striker = uuid4()

    result = advance_batters(
        striker,
        non_striker,
        runs=0,
        legal_balls_after=6,
        balls_per_over=6,
    )

    assert result == (non_striker, striker)


def test_odd_last_ball_swaps_twice() -> None:
    striker = uuid4()
    non_striker = uuid4()

    result = advance_batters(
        striker,
        non_striker,
        runs=1,
        legal_balls_after=6,
        balls_per_over=6,
    )

    assert result == (striker, non_striker)


def test_overs_display() -> None:
    assert overs_display(8, 6) == "1.2"


def test_run_rate() -> None:
    assert current_run_rate(10, 8, 6) == 7.5


def test_history_rebuild() -> None:
    opening_striker = uuid4()
    opening_non_striker = uuid4()

    innings = SimpleNamespace(
        striker_id=uuid4(),
        non_striker_id=uuid4(),
    )

    deliveries = [
        SimpleNamespace(
            total_runs=1,
            is_legal_ball=True,
            striker_id=opening_striker,
            non_striker_id=opening_non_striker,
        ),
        SimpleNamespace(
            total_runs=4,
            is_legal_ball=True,
            striker_id=opening_non_striker,
            non_striker_id=opening_striker,
        ),
    ]

    result = rebuild_from_deliveries(
        innings,
        deliveries,
        balls_per_over=6,
    )

    assert result.total_runs == 5
    assert result.legal_balls == 2
    assert result.striker_id == opening_non_striker
    assert result.non_striker_id == opening_striker

def test_same_bowler_cannot_start_next_over() -> None:
    bowler = uuid4()

    assert bowler_change_required(
        legal_balls=6,
        balls_per_over=6,
        previous_bowler_id=bowler,
        current_bowler_id=bowler,
    )


def test_new_bowler_clears_over_boundary() -> None:
    assert not bowler_change_required(
        legal_balls=6,
        balls_per_over=6,
        previous_bowler_id=uuid4(),
        current_bowler_id=uuid4(),
    )


def test_no_bowler_change_mid_over_or_before_first_ball() -> None:
    bowler = uuid4()

    for legal_balls in (0, 3, 7):
        assert not bowler_change_required(
            legal_balls=legal_balls,
            balls_per_over=6,
            previous_bowler_id=bowler,
            current_bowler_id=bowler,
        )


def test_previous_over_bowler_is_last_legal_ball() -> None:
    first = uuid4()
    second = uuid4()

    deliveries = [
        SimpleNamespace(bowler_id=first, is_legal_ball=True),
        SimpleNamespace(bowler_id=second, is_legal_ball=True),
    ]

    assert previous_over_bowler_id(deliveries) == second
    assert previous_over_bowler_id([]) is None


def test_max_innings() -> None:
    assert max_innings(1) == 2
    assert max_innings(2) == 4


def test_chase_target() -> None:
    assert chase_target(opponent_runs=150, batting_previous_runs=0) == 151
    # Multi-innings: runs from earlier innings count.
    assert chase_target(opponent_runs=300, batting_previous_runs=200) == 101


def test_result_summary() -> None:
    common = dict(
        batting_team_name="Chasers",
        bowling_team_name="Defenders",
        players_per_side=11,
    )

    assert result_summary(
        batting_runs=151, bowling_runs=150, wickets=3, **common
    ) == "Chasers won by 7 wickets"

    assert result_summary(
        batting_runs=149, bowling_runs=150, wickets=0, **common
    ) == "Defenders won by 1 run"

    assert result_summary(
        batting_runs=150, bowling_runs=150, wickets=0, **common
    ) == "Match tied"
