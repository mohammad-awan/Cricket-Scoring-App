"""Teams may field fewer than a full side (gully, indoor, short-handed club)."""

from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions import ValidationError
from app.domain.batting_order import validate_batting_order
from app.domain.playing_side import (
    batting_side_size,
    minimum_players,
    side_size_allowed,
    side_size_text,
)
from app.domain.tournament_rules import TournamentRules, match_config_from_rules
from app.schemas.match_setup import MatchCreate
from app.services.scoring.calculations import max_wickets
from app.services.scoring.chase import result_summary


def _match(players_per_side=11, minimum=None):
    return SimpleNamespace(players_per_side=players_per_side, minimum_players_to_start=minimum)


def _selections(count):
    return [SimpleNamespace(player_id=uuid4(), batting_order=position) for position in range(1, count + 1)]


def test_full_side_is_required_by_default() -> None:
    match = _match()

    assert minimum_players(match) == 11
    assert side_size_allowed(match, 11)
    assert not side_size_allowed(match, 10)
    assert side_size_text(match) == "exactly 11"


def test_short_sides_are_allowed_down_to_the_minimum() -> None:
    match = _match(11, 6)

    assert [count for count in range(4, 14) if side_size_allowed(match, count)] == [6, 7, 8, 9, 10, 11]
    assert side_size_text(match) == "between 6 and 11"


def test_batting_order_accepts_a_short_side_with_positions_one_to_n() -> None:
    ordered = validate_batting_order(_selections(6), players_per_side=11, minimum_players=6)

    assert len(ordered) == 6

    with pytest.raises(ValidationError):
        validate_batting_order(_selections(5), players_per_side=11, minimum_players=6)

    with pytest.raises(ValidationError):
        validate_batting_order(_selections(12), players_per_side=11, minimum_players=6)

    # Without a minimum the old full-side rule applies.
    with pytest.raises(ValidationError):
        validate_batting_order(_selections(6), players_per_side=11)


def test_batting_positions_must_run_one_to_n_for_the_side_fielded() -> None:
    selections = _selections(6)
    selections[-1].batting_order = 11

    with pytest.raises(ValidationError, match="1 to 6"):
        validate_batting_order(selections, players_per_side=11, minimum_players=6)


def test_all_out_follows_the_batting_side_actually_fielded() -> None:
    match = _match(11, 6)

    assert max_wickets(batting_side_size(match, SimpleNamespace(batting_side_size=6))) == 5
    assert max_wickets(batting_side_size(match, SimpleNamespace(batting_side_size=11))) == 10
    # Innings created before this change fall back to a full side.
    assert max_wickets(batting_side_size(match, SimpleNamespace(batting_side_size=None))) == 10


def test_winning_margin_counts_wickets_left_in_a_short_side() -> None:
    summary = result_summary(
        batting_team_name="Strikers",
        bowling_team_name="Kings",
        batting_runs=60,
        bowling_runs=58,
        wickets=2,
        players_per_side=6,
    )

    assert summary == "Strikers won by 3 wickets"


def test_match_minimum_cannot_exceed_the_full_side() -> None:
    base = {"team_a_id": uuid4(), "team_b_id": uuid4(), "players_per_side": 8}

    assert MatchCreate(**base, minimum_players_to_start=5).minimum_players_to_start == 5
    assert MatchCreate(**base).minimum_players_to_start is None

    with pytest.raises(PydanticValidationError):
        MatchCreate(**base, minimum_players_to_start=9)


def test_tournament_rules_allow_squads_smaller_than_a_full_side() -> None:
    rules = TournamentRules(
        players_per_side=11,
        minimum_players_to_start=6,
        minimum_roster_size=6,
        maximum_roster_size=18,
    )

    assert match_config_from_rules(rules)["minimum_players_to_start"] == 6

    with pytest.raises(PydanticValidationError):
        TournamentRules(players_per_side=11, minimum_players_to_start=6, minimum_roster_size=5)


def test_fixed_bowler_quota_must_cover_the_overs_for_a_short_side() -> None:
    # 6 players x 3 overs = 18 overs, short of 20.
    with pytest.raises(PydanticValidationError):
        TournamentRules(
            minimum_players_to_start=6,
            minimum_roster_size=6,
            bowler_quota_policy="fixed",
            overs_per_bowler=3,
        )

    TournamentRules(
        minimum_players_to_start=6,
        minimum_roster_size=6,
        bowler_quota_policy="fixed",
        overs_per_bowler=4,
    )
