
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.core.exceptions import ValidationError
from app.domain.batting_order import select_next_batter, validate_batting_order
from app.domain.bowling import bowler_ball_quota, validate_bowler_quota
from app.domain.wickets import resolve_dismissed_player, validate_fielder, validate_wicket_delivery
from app.models.enums import MatchType, WicketType


@pytest.fixture
def players():
    return [uuid4() for _ in range(11)]


def test_valid_batting_order(players):
    selections = [
        SimpleNamespace(player_id=player_id, batting_order=index)
        for index, player_id in enumerate(players, start=1)
    ]

    assert validate_batting_order(selections, players_per_side=11) == players


def test_incomplete_batting_order_rejected(players):
    selections = [
        SimpleNamespace(player_id=player_id, batting_order=index)
        for index, player_id in enumerate(players, start=1)
    ]

    selections[5].batting_order = None

    with pytest.raises(ValidationError):
        validate_batting_order(selections, players_per_side=11)


def test_next_batter_automatically_selected(players):
    result = select_next_batter(
        players,
        striker_id=players[0],
        non_striker_id=players[1],
        dismissed_player_ids=set(),
        dismissed_player_id=players[0],
    )

    assert result == players[2]


def test_next_batter_skips_dismissed(players):
    result = select_next_batter(
        players,
        striker_id=players[0],
        non_striker_id=players[1],
        dismissed_player_ids={players[2], players[3]},
        dismissed_player_id=players[0],
    )

    assert result == players[4]


def test_final_wicket_has_no_next_batter(players):
    result = select_next_batter(
        players,
        striker_id=players[9],
        non_striker_id=players[10],
        dismissed_player_ids=set(players[:9]),
        dismissed_player_id=players[9],
        final_wicket=True,
    )

    assert result is None


@pytest.mark.parametrize(
    "wicket_type",
    [
        WicketType.BOWLED,
        WicketType.CAUGHT,
        WicketType.LBW,
        WicketType.STUMPED,
        WicketType.HIT_WICKET,
    ],
)
def test_striker_dismissal_is_automatic(players, wicket_type):
    result = resolve_dismissed_player(
        wicket_type=wicket_type,
        striker_id=players[0],
        non_striker_id=players[1],
        requested_player_id=None,
    )

    assert result == players[0]


@pytest.mark.parametrize(
    "wicket_type",
    [
        WicketType.BOWLED,
        WicketType.LBW,
        WicketType.HIT_WICKET,
    ],
)
def test_forbidden_fielder_rejected(players, wicket_type):
    with pytest.raises(ValidationError):
        validate_fielder(
            wicket_type=wicket_type,
            fielder_id=players[2],
            bowling_xi_ids={players[2]},
        )


@pytest.mark.parametrize(
    "wicket_type",
    [
        WicketType.CAUGHT,
        WicketType.STUMPED,
        WicketType.RUN_OUT,
    ],
)
def test_required_fielder_rejected_when_missing(wicket_type):
    with pytest.raises(ValidationError):
        validate_fielder(
            wicket_type=wicket_type,
            fielder_id=None,
            bowling_xi_ids={uuid4()},
        )


def test_valid_catch_fielder(players):
    validate_fielder(
        wicket_type=WicketType.CAUGHT,
        fielder_id=players[2],
        bowling_xi_ids={players[2]},
    )


@pytest.mark.parametrize(
    "wicket_type",
    [
        WicketType.BOWLED,
        WicketType.CAUGHT,
        WicketType.LBW,
        WicketType.STUMPED,
        WicketType.HIT_WICKET,
    ],
)
def test_no_ball_rejects_ordinary_dismissals(wicket_type):
    with pytest.raises(ValidationError):
        validate_wicket_delivery(
            wicket_type=wicket_type,
            no_ball=True,
            wide_runs=0,
            running_runs=0,
            wicket_end=None,
        )


def test_run_out_allowed_on_no_ball():
    validate_wicket_delivery(
        wicket_type=WicketType.RUN_OUT,
        no_ball=True,
        wide_runs=0,
        running_runs=1,
        wicket_end="striker_end",
    )


def test_run_out_requires_wicket_end():
    with pytest.raises(ValidationError):
        validate_wicket_delivery(
            wicket_type=WicketType.RUN_OUT,
            no_ball=False,
            wide_runs=0,
            running_runs=1,
            wicket_end=None,
        )


def test_t20_bowler_quota():
    match = SimpleNamespace(
        match_type=MatchType.T20,
        total_overs=20,
        balls_per_over=6,
    )

    assert bowler_ball_quota(match) == 24


def test_odi_bowler_quota():
    match = SimpleNamespace(
        match_type=MatchType.ODI,
        total_overs=50,
        balls_per_over=6,
    )

    assert bowler_ball_quota(match) == 60


def test_bowler_quota_is_enforced():
    bowler_id = uuid4()

    match = SimpleNamespace(
        match_type=MatchType.T20,
        total_overs=20,
        balls_per_over=6,
    )

    deliveries = [
        SimpleNamespace(
            bowler_id=bowler_id,
            is_legal_ball=True,
        )
        for _ in range(24)
    ]

    with pytest.raises(ValidationError):
        validate_bowler_quota(
            match=match,
            deliveries=deliveries,
            bowler_id=bowler_id,
        )


def test_test_match_has_no_bowler_quota():
    match = SimpleNamespace(
        match_type=MatchType.TEST,
        total_overs=None,
        balls_per_over=6,
    )

    assert bowler_ball_quota(match) is None


def test_scorer_can_promote_power_hitter(players):
    selected = select_next_batter(
        players,
        striker_id=players[0],
        non_striker_id=players[1],
        dismissed_player_ids=set(),
        dismissed_player_id=players[0],
        selection_mode="manual",
        manual_player_id=players[7],
    )

    assert selected == players[7]


def test_dismissed_batter_cannot_return(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[0],
            non_striker_id=players[1],
            dismissed_player_ids={players[7]},
            dismissed_player_id=players[0],
            selection_mode="manual",
            manual_player_id=players[7],
        )


def test_batter_at_crease_cannot_be_selected(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[0],
            non_striker_id=players[1],
            dismissed_player_ids=set(),
            dismissed_player_id=players[0],
            selection_mode="manual",
            manual_player_id=players[1],
        )


def test_player_outside_playing_xi_cannot_be_selected(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[0],
            non_striker_id=players[1],
            dismissed_player_ids=set(),
            dismissed_player_id=players[0],
            selection_mode="manual",
            manual_player_id=uuid4(),
        )


def test_manual_mode_requires_selection(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[0],
            non_striker_id=players[1],
            dismissed_player_ids=set(),
            dismissed_player_id=players[0],
            selection_mode="manual",
        )


def test_automatic_mode_rejects_manual_id(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[0],
            non_striker_id=players[1],
            dismissed_player_ids=set(),
            dismissed_player_id=players[0],
            manual_player_id=players[7],
        )


def test_final_wicket_rejects_incoming_batter(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[9],
            non_striker_id=players[10],
            dismissed_player_ids=set(players[:9]),
            dismissed_player_id=players[9],
            selection_mode="manual",
            manual_player_id=players[2],
            final_wicket=True,
        )


def test_skip_player_then_select_them_later(players):
    promoted = select_next_batter(
        players,
        striker_id=players[0],
        non_striker_id=players[1],
        dismissed_player_ids=set(),
        dismissed_player_id=players[0],
        selection_mode="manual",
        manual_player_id=players[7],
    )

    assert promoted == players[7]

    # Next wicket: the promoted batter is out. The originally
    # scheduled batter is still first in line automatically.
    after_next_wicket = select_next_batter(
        players,
        striker_id=promoted,
        non_striker_id=players[1],
        dismissed_player_ids={players[0]},
        dismissed_player_id=promoted,
    )

    assert after_next_wicket == players[2]


def test_automatic_selection_skips_promoted_batter(players):
    # players[7] was promoted earlier and is now at the crease.
    selected = select_next_batter(
        players,
        striker_id=players[7],
        non_striker_id=players[1],
        dismissed_player_ids={players[0], players[2]},
        dismissed_player_id=players[1],
    )

    assert selected == players[3]


def test_schema_rejects_next_batter_in_automatic_mode():
    from pydantic import ValidationError as PydanticValidationError

    from app.schemas.scoring import WicketCreate

    with pytest.raises(PydanticValidationError):
        WicketCreate(wicket_type=WicketType.BOWLED, next_batter_id=uuid4())

    manual = WicketCreate(
        wicket_type=WicketType.BOWLED,
        selection_mode="manual",
        next_batter_id=uuid4(),
    )
    assert manual.selection_mode == "manual"
