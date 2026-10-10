from datetime import UTC, date, datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.models import (
    BattingHand,
    BowlingArm,
    BowlingStyle,
    WicketType,
)
from app.repositories.player_profile import PlayerActivityRow
from app.schemas.players import PlayerCreate
from app.services.player_profile import (
    build_batting,
    build_bowling,
    batting_style_display,
    bowling_style_display,
    calculate_age,
)


def activity_row(
    *,
    player_id,
    striker_id=None,
    bowler_id=None,
    batter_runs=0,
    wide_runs=0,
    no_ball_runs=0,
    legal=True,
    wicket_type=None,
    dismissed_player_id=None,
    match_id=None,
    innings_id=None,
    innings_number=1,
):

    other = uuid4()
    return PlayerActivityRow(

        match_id=match_id or uuid4(),
        innings_id=innings_id or uuid4(),
        innings_number=innings_number,
        scheduled_at=datetime(
            2026,
            10,
            1,
            tzinfo=UTC,
        ),
        match_created_at=datetime(
            2026,
            9,
            30,
            tzinfo=UTC,
        ),
        balls_per_over=6,
        striker_id=striker_id or other,
        bowler_id=bowler_id or other,
        batter_runs=batter_runs,
        wide_runs=wide_runs,
        no_ball_runs=no_ball_runs,
        bye_runs=0,
        leg_bye_runs=0,
        is_legal_ball=legal,
        wicket_type=wicket_type,
        dismissed_player_id=dismissed_player_id,
    )


def test_age_is_derived_not_stored():
    assert (
        calculate_age(
            date(
                2000,
                10,
                7,
            ),
            today=date(
                2026,
                10,
                6,
            ),
        )
        == 25
    )

    assert (
        calculate_age(
            date(
                2000,
                10,
                6,
            ),
            today=date(
                2026,
                10,
                6,
            ),
        )
        == 26
    )


def test_future_date_of_birth_is_rejected():

    with pytest.raises(ValidationError):
        PlayerCreate(
            full_name="Future Player",
            date_of_birth=date(
                2099,
                1,
                1,
            ),
        )


def test_normalized_style_display():
    assert (
        batting_style_display(BattingHand.RIGHT)
        ==
        "Right-hand batter"
    )
    assert (
        bowling_style_display(
            BowlingArm.LEFT,
            BowlingStyle.ORTHODOX,
        )
        ==
        "Left-arm orthodox"
    )
    assert (
        bowling_style_display(
            BowlingArm.NONE,
            None,
        )
        ==
        "Does not bowl"
    )


def test_batting_statistics_use_delivery_denominators():
    player_id = uuid4()
    match_id = uuid4()
    innings_id = uuid4()
    rows = [

        activity_row(
            player_id=player_id,
            striker_id=player_id,
            batter_runs=4,
            match_id=match_id,
            innings_id=innings_id,
        ),

        activity_row(
            player_id=player_id,
            striker_id=player_id,
            batter_runs=6,
            match_id=match_id,
            innings_id=innings_id,
        ),

        activity_row(
            player_id=player_id,
            striker_id=player_id,
            wide_runs=1,
            legal=False,
            match_id=match_id,
            innings_id=innings_id,
        ),

        activity_row(
            player_id=player_id,
            striker_id=player_id,
            batter_runs=0,
            wicket_type=(
                WicketType.BOWLED
            ),
            dismissed_player_id=(
                player_id
            ),
            match_id=match_id,
            innings_id=innings_id,
        ),

    ]

    career, _ = (
        build_batting(
            player_id,
            rows,
        )
    )

    assert career.runs == 10
    assert career.balls_faced == 3
    assert career.dismissals == 1
    assert career.average == 10.0
    assert career.strike_rate == 333.33
    assert career.fours == 1
    assert career.sixes == 1


def test_bowling_excludes_run_out_from_bowler_wickets():
    player_id = uuid4()
    match_id = uuid4()
    innings_id = uuid4()
    rows = [

        activity_row(
            player_id=player_id,
            bowler_id=player_id,
            batter_runs=1,
            match_id=match_id,
            innings_id=innings_id,
        ),

        activity_row(
            player_id=player_id,
            bowler_id=player_id,
            batter_runs=0,
            wicket_type=(
                WicketType.BOWLED
            ),
            dismissed_player_id=(
                uuid4()
            ),
            match_id=match_id,
            innings_id=innings_id,
        ),

        activity_row(
            player_id=player_id,
            bowler_id=player_id,
            batter_runs=0,
            wicket_type=(
                WicketType.RUN_OUT
            ),
            dismissed_player_id=(
                uuid4()
            ),
            match_id=match_id,
            innings_id=innings_id,
        ),

    ]


    career, _ = (
        build_bowling(
            player_id,
            rows,
        )
    )


    assert career.wickets == 1
    assert career.runs_conceded == 1
    assert career.balls_bowled == 3
    assert career.average == 1.0
    assert career.strike_rate == 3.0