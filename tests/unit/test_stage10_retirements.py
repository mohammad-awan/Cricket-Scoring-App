from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions import ValidationError
from app.domain.batting_order import select_next_batter
from app.domain.retirements import (
    crease_after_retirement,
    retirement_status,
    validate_retiring_player,
)
from app.models.enums import RetirementType
from app.repositories.scorecard import RetirementScoreRow
from app.schemas.batting_order import LiveBattingOrderUpdate
from app.schemas.retirements import RetirementCreate
from app.services.scorecard.batting import retirement_labels
from app.services.scorecard.innings import innings_totals
from app.services.scoring.batting_order import entered_player_ids
from app.services.scoring.state import rebuild_innings_state, trailing_retirements
from app.services.scoring.types import DerivedState


@pytest.fixture
def players():
    return [uuid4() for _ in range(11)]


def _delivery(number, striker, non_striker, *, runs=0, legal=True, dismissed=None, next_batter=None):
    return SimpleNamespace(
        delivery_number=number,
        striker_id=striker,
        non_striker_id=non_striker,
        total_runs=runs,
        batter_runs=runs,
        bye_runs=0,
        leg_bye_runs=0,
        wide_runs=0,
        is_legal_ball=legal,
        dismissed_player_id=dismissed,
        wicket_type="bowled" if dismissed else None,
        next_batter_id=next_batter,
        wicket_end=None,
    )


def _retirement(
    number,
    after,
    player,
    kind,
    *,
    before,
    after_crease,
    replacement=None,
):
    return SimpleNamespace(
        event_number=number,
        after_delivery_number=after,
        player_id=player,
        retirement_type=kind,
        replacement_player_id=replacement,
        striker_before_id=before[0],
        non_striker_before_id=before[1],
        striker_after_id=after_crease[0],
        non_striker_after_id=after_crease[1],
    )


def _innings(striker, non_striker):
    return SimpleNamespace(striker_id=striker, non_striker_id=non_striker)


# ======================
# Crease transitions
# ======================


def test_striker_retirement_replaced_at_striker_end(players):
    assert crease_after_retirement(
        striker_id=players[0],
        non_striker_id=players[1],
        retiring_player_id=players[0],
        replacement_player_id=players[2],
    ) == (players[2], players[1])


def test_non_striker_retirement_replaced_at_non_striker_end(players):
    assert crease_after_retirement(
        striker_id=players[0],
        non_striker_id=players[1],
        retiring_player_id=players[1],
        replacement_player_id=players[2],
    ) == (players[0], players[2])


def test_final_retired_out_keeps_retiring_batter_in_state(players):
    assert crease_after_retirement(
        striker_id=players[0],
        non_striker_id=players[1],
        retiring_player_id=players[0],
        replacement_player_id=None,
    ) == (players[0], players[1])


def test_only_crease_batter_can_retire(players):
    with pytest.raises(ValidationError):
        validate_retiring_player(players[5], striker_id=players[0], non_striker_id=players[1])


# ======================
# Retirement status
# ======================


def test_retired_hurt_is_resumable_and_retired_out_is_dismissed(players):
    events = [
        SimpleNamespace(player_id=players[0], retirement_type=RetirementType.HURT),
        SimpleNamespace(player_id=players[1], retirement_type=RetirementType.OUT),
    ]

    status = retirement_status(
        events,
        crease_ids={players[2], players[3]},
        dismissed_ids=set(),
    )

    assert status.retired_hurt_ids == {players[0]}
    assert status.retired_out_ids == {players[1]}


def test_resumed_batter_no_longer_retired_hurt(players):
    events = [SimpleNamespace(player_id=players[0], retirement_type=RetirementType.HURT)]

    at_crease = retirement_status(events, crease_ids={players[0], players[2]}, dismissed_ids=set())
    dismissed_later = retirement_status(events, crease_ids={players[2], players[3]}, dismissed_ids={players[0]})

    assert at_crease.retired_hurt_ids == frozenset()
    assert dismissed_later.retired_hurt_ids == frozenset()


def test_resumed_then_retired_out(players):
    events = [
        SimpleNamespace(player_id=players[0], retirement_type=RetirementType.HURT),
        SimpleNamespace(player_id=players[0], retirement_type=RetirementType.OUT),
    ]

    status = retirement_status(events, crease_ids={players[2], players[3]}, dismissed_ids=set())

    assert status.retired_hurt_ids == frozenset()
    assert status.retired_out_ids == {players[0]}


# ======================
# Incoming batter with retirements
# ======================


def test_automatic_selection_skips_retired_hurt(players):
    selected = select_next_batter(
        players,
        striker_id=players[2],
        non_striker_id=players[1],
        dismissed_player_ids=set(),
        dismissed_player_id=players[1],
        resumable_player_ids={players[0]},
    )

    assert selected == players[3]


def test_retired_hurt_batter_can_resume_manually(players):
    selected = select_next_batter(
        players,
        striker_id=players[2],
        non_striker_id=players[1],
        dismissed_player_ids=set(),
        dismissed_player_id=players[1],
        selection_mode="manual",
        manual_player_id=players[0],
        resumable_player_ids={players[0]},
    )

    assert selected == players[0]


def test_automatic_requires_choice_when_only_retired_hurt_remain(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[9],
            non_striker_id=players[10],
            dismissed_player_ids=set(players[1:9]),
            dismissed_player_id=players[9],
            resumable_player_ids={players[0]},
        )


def test_retired_out_batter_cannot_return(players):
    with pytest.raises(ValidationError):
        select_next_batter(
            players,
            striker_id=players[2],
            non_striker_id=players[1],
            dismissed_player_ids={players[0]},
            dismissed_player_id=players[1],
            selection_mode="manual",
            manual_player_id=players[0],
        )


# ======================
# Unified replay
# ======================


def test_retirement_after_last_delivery_sets_crease(players):
    a, b, c = players[:3]
    deliveries = [_delivery(1, a, b, runs=2)]
    retirements = [
        _retirement(1, 1, a, RetirementType.HURT, before=(a, b), after_crease=(c, b), replacement=c),
    ]

    state = rebuild_innings_state(_innings(a, b), deliveries, retirements, balls_per_over=6)

    assert (state.striker_id, state.non_striker_id) == (c, b)
    assert state.wickets == 0
    assert state.total_runs == 2
    assert state.legal_balls == 1


def test_retired_out_counts_as_wicket(players):
    a, b, c = players[:3]
    deliveries = [_delivery(1, a, b)]
    retirements = [
        _retirement(1, 1, b, RetirementType.OUT, before=(a, b), after_crease=(a, c), replacement=c),
    ]

    state = rebuild_innings_state(_innings(a, b), deliveries, retirements, balls_per_over=6)

    assert state.wickets == 1
    assert state.non_striker_id == c


def test_earlier_retirement_is_superseded_by_later_delivery(players):
    a, b, c = players[:3]
    deliveries = [
        _delivery(1, a, b),
        # Recorded after the retirement, with c batting.
        _delivery(2, c, b, runs=1),
    ]
    retirements = [
        _retirement(1, 1, a, RetirementType.HURT, before=(a, b), after_crease=(c, b), replacement=c),
    ]

    state = rebuild_innings_state(_innings(a, b), deliveries, retirements, balls_per_over=6)

    # Single run rotates strike from delivery 2.
    assert (state.striker_id, state.non_striker_id) == (b, c)


def test_undo_delivery_after_retirement_restores_retirement_state(players):
    a, b, c = players[:3]
    # Delivery 2 has been voided; only delivery 1 remains.
    deliveries = [_delivery(1, a, b)]
    retirements = [
        _retirement(1, 1, a, RetirementType.HURT, before=(a, b), after_crease=(c, b), replacement=c),
    ]

    state = rebuild_innings_state(_innings(a, b), deliveries, retirements, balls_per_over=6)

    assert (state.striker_id, state.non_striker_id) == (c, b)


def test_retirement_before_first_ball(players):
    a, b, c = players[:3]
    retirements = [
        _retirement(1, 0, b, RetirementType.HURT, before=(a, b), after_crease=(a, c), replacement=c),
    ]

    state = rebuild_innings_state(_innings(a, b), [], retirements, balls_per_over=6)

    assert (state.striker_id, state.non_striker_id) == (a, c)


def test_consecutive_retirements_use_latest(players):
    a, b, c, d = players[:4]
    deliveries = [_delivery(1, a, b)]
    retirements = [
        _retirement(1, 1, a, RetirementType.HURT, before=(a, b), after_crease=(c, b), replacement=c),
        _retirement(2, 1, b, RetirementType.HURT, before=(c, b), after_crease=(c, d), replacement=d),
    ]

    state = rebuild_innings_state(_innings(a, b), deliveries, retirements, balls_per_over=6)

    assert (state.striker_id, state.non_striker_id) == (c, d)
    assert trailing_retirements(deliveries, retirements) == retirements


def test_no_retirements_matches_delivery_replay(players):
    a, b = players[:2]
    deliveries = [_delivery(1, a, b, runs=1)]

    state = rebuild_innings_state(_innings(a, b), deliveries, [], balls_per_over=6)

    assert (state.striker_id, state.non_striker_id) == (b, a)


# ======================
# Lineup locking
# ======================


def test_entered_players_are_locked(players):
    a, b, c, d = players[:4]
    deliveries = [_delivery(1, a, b, dismissed=a, next_batter=c)]
    retirements = [
        _retirement(1, 1, b, RetirementType.HURT, before=(c, b), after_crease=(c, d), replacement=d),
    ]
    derived = DerivedState(total_runs=0, legal_balls=1, wickets=1, striker_id=c, non_striker_id=d)

    assert entered_player_ids(deliveries, retirements, derived) == {a, b, c, d}


# ======================
# Scorecard
# ======================


def _score_delivery(number, striker, non_striker, *, dismissed=None, next_batter=None):
    return SimpleNamespace(
        delivery_number=number,
        striker_id=striker,
        non_striker_id=non_striker,
        dismissed_player_id=dismissed,
        next_batter_id=next_batter,
        total_runs=0,
        is_legal_ball=True,
    )


def test_scorecard_labels_retired_hurt_and_out(players):
    a, b, c, d = players[:4]
    deliveries = [_score_delivery(1, a, b)]
    retirements = [
        RetirementScoreRow(1, 1, a, "retired_hurt", c),
        RetirementScoreRow(2, 1, b, "retired_out", d),
    ]

    labels = retirement_labels(deliveries, retirements)

    assert labels == {a: "retired hurt", b: "retired out"}


def test_scorecard_resumed_batter_is_not_retired_hurt(players):
    a, b, c = players[:3]
    deliveries = [
        _score_delivery(1, a, b),
        _score_delivery(2, c, b, dismissed=c, next_batter=a),
    ]
    retirements = [RetirementScoreRow(1, 1, a, "retired_hurt", c)]

    assert retirement_labels(deliveries, retirements) == {}


def test_retired_out_counts_in_team_total_not_bowler(players):
    a, b, c = players[:3]
    deliveries = [_score_delivery(1, a, b)]
    retirements = [RetirementScoreRow(1, 1, a, "retired_out", c)]

    assert innings_totals(deliveries, retirements).wickets == 1
    assert innings_totals(deliveries).wickets == 0


# ======================
# Schemas
# ======================


def test_retirement_automatic_mode_rejects_replacement():
    with pytest.raises(PydanticValidationError):
        RetirementCreate(
            player_id=uuid4(),
            retirement_type=RetirementType.HURT,
            replacement_player_id=uuid4(),
            reason="Hamstring injury",
        )


def test_retirement_manual_mode_accepts_replacement():
    payload = RetirementCreate(
        player_id=uuid4(),
        retirement_type=RetirementType.OUT,
        selection_mode="manual",
        replacement_player_id=uuid4(),
        reason="Tactical retirement",
    )

    assert payload.selection_mode == "manual"


def test_batting_order_update_rejects_duplicates():
    player = uuid4()

    with pytest.raises(PydanticValidationError):
        LiveBattingOrderUpdate(ordered_player_ids=[player, player], reason="Promote hitter")
