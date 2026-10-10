from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.models.enums import WicketType
from app.schemas.scoring import DeliveryCreate, WicketCreate
from app.services.scoring.calculations import post_delivery_batters
from app.services.scoring import (
    delivery_components,
    max_wickets,
    rebuild_from_deliveries,
)


def test_wide_is_illegal_and_all_runs_are_extras() -> None:
    components = (
        delivery_components(
            DeliveryCreate(
                wide_runs=3
            )
        )
    )
    assert components.batter_runs == 0
    assert components.extra_runs  == 3
    assert components.total_runs == 3
    assert components.running_runs == 2
    assert not components.is_legal_ball


def test_no_ball_has_automatic_extra() -> None:
    components = (
        delivery_components(
            DeliveryCreate(
                runs=4,
                no_ball=True,
            )
        )
    )
    assert components.batter_runs == 4
    assert components.no_ball_runs == 1
    assert components.extra_runs == 1
    assert components.total_runs == 5
    assert components.running_runs == 4
    assert not components.is_legal_ball


def test_bye_and_leg_bye_are_legal_balls() -> None:
    bye = (
        delivery_components(
            DeliveryCreate(
                bye_runs=2
            )
        )
    )
    leg_bye = (
        delivery_components(
            DeliveryCreate(
                leg_bye_runs=1
            )
        )
    )
    assert bye.is_legal_ball
    assert bye.total_runs == 2
    assert bye.running_runs == 2
    assert leg_bye.is_legal_ball
    assert leg_bye.total_runs == 1
    assert leg_bye.running_runs == 1


def test_no_ball_can_be_combined_with_byes() -> None:
    components = (
        delivery_components(
            DeliveryCreate(
                no_ball=True,
                bye_runs=2,
            )
        )
    )
    assert (components.total_runs == 3)
    assert (components.extra_runs == 3)
    assert (components.running_runs == 2)
    assert not (components.is_legal_ball)


def test_invalid_extra_combinations_are_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        DeliveryCreate(runs=1, wide_runs=1)

    with pytest.raises(PydanticValidationError):
        DeliveryCreate(bye_runs=1, leg_bye_runs=1)

    with pytest.raises(PydanticValidationError):
        DeliveryCreate(runs=1, bye_runs=1)


def test_wicket_end_only_allowed_for_run_out() -> None:
    player_id = uuid4()
    with pytest.raises(PydanticValidationError):
        WicketCreate(
            wicket_type=WicketType.BOWLED,
            dismissed_player_id=player_id,
            wicket_end=("striker_end"),
        )

    wicket = WicketCreate(
        wicket_type=WicketType.RUN_OUT,
        dismissed_player_id=player_id,
        wicket_end=("non_striker_end"),
    )

    assert wicket.wicket_end == "non_striker_end"


def test_illegal_ball_does_not_complete_over() -> None:
    striker = uuid4()
    non_striker = uuid4()
    after = (
        post_delivery_batters(
            striker_id=(
                striker
            ),
            non_striker_id=(
                non_striker
            ),
            running_runs=0,
            is_legal_ball=False,
            legal_balls_after=6,
            balls_per_over=6,
        )
    )

    assert after == (striker, non_striker)


def test_wicket_on_last_ball_changes_ends() -> None:
    striker = uuid4()
    non_striker = uuid4()
    next_batter = uuid4()
    after = (
        post_delivery_batters(
            striker_id=striker,
            non_striker_id=non_striker,
            running_runs=0,
            is_legal_ball=True,
            legal_balls_after=6,
            balls_per_over=6,
            dismissed_player_id=striker,
            next_batter_id=next_batter,
        )
    )

    assert after == (non_striker, next_batter)


def test_history_rebuild_with_extra() -> None:
    striker = uuid4()
    non_striker = uuid4()
    innings = SimpleNamespace(striker_id=(striker), non_striker_id=(non_striker))
    deliveries = [
        SimpleNamespace(
            total_runs=1,
            batter_runs=0,
            wide_runs=1,
            no_ball_runs=0,
            bye_runs=0,
            leg_bye_runs=0,
            is_legal_ball=False,
            striker_id=striker,
            non_striker_id=non_striker,
            dismissed_player_id=None,
            wicket_type=None,
            next_batter_id=None,
            wicket_end=None,
        ),
        SimpleNamespace(
            total_runs=1,
            batter_runs=1,
            wide_runs=0,
            no_ball_runs=0,
            bye_runs=0,
            leg_bye_runs=0,
            is_legal_ball=True,
            striker_id=striker,
            non_striker_id=(
                non_striker
            ),
            dismissed_player_id=None,
            wicket_type=None,
            next_batter_id=None,
            wicket_end=None,
        ),
    ]

    result = (
        rebuild_from_deliveries(
            innings,
            deliveries,
            balls_per_over=6,
        )
    )
    assert (result.total_runs == 2)
    assert (result.legal_balls == 1)
    assert (result.wickets == 0)
    assert (result.striker_id == non_striker)
    assert (result.non_striker_id == striker)


def test_max_wickets() -> None:
    assert (max_wickets(11) == 10)
    assert (max_wickets(2) == 1)