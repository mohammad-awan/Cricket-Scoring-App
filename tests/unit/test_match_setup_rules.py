from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.models.enums import TossDecision
from app.schemas.match_setup import (
    MatchCreate,
    OpeningInningsSetup,
    PlayingTeamPlayer,
    PlayingTeamSetup,
)
from app.services.match_setup import _readiness, derive_first_innings_teams


TEAM_A = uuid4()
TEAM_B = uuid4()


def make_match(**overrides):
    values = {
        "team_a_id": TEAM_A,
        "team_b_id": TEAM_B,
        "venue_id": uuid4(),
        "scheduled_at": datetime.now(UTC),
        "toss_winner_id": None,
        "toss_decision": None,
        "players_per_side": 2,
        "players": [],
        "innings": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def selection(team_id):
    return SimpleNamespace(team_id=team_id, player_id=uuid4())


def test_toss_winner_batting_first() -> None:
    match = make_match(toss_winner_id=TEAM_B, toss_decision=TossDecision.BAT)

    assert derive_first_innings_teams(match) == (TEAM_B, TEAM_A)


def test_toss_winner_bowling_first() -> None:
    match = make_match(toss_winner_id=TEAM_A, toss_decision=TossDecision.BOWL)

    assert derive_first_innings_teams(match) == (TEAM_B, TEAM_A)


def test_innings_teams_require_toss() -> None:
    with pytest.raises(ValidationError):
        derive_first_innings_teams(make_match())


def test_toss_winner_must_belong_to_match() -> None:
    match = make_match(toss_winner_id=uuid4(), toss_decision=TossDecision.BAT)

    with pytest.raises(ValidationError):
        derive_first_innings_teams(match)


def test_new_match_reports_everything_missing() -> None:
    readiness = _readiness(make_match(venue_id=None, scheduled_at=None))

    assert not readiness.ready
    assert readiness.missing == [
        "venue",
        "scheduled_at",
        "toss",
        "team_a_playing_team",
        "team_b_playing_team",
        "opening_innings",
    ]


def test_complete_setup_is_ready() -> None:
    team_a_xi = [selection(TEAM_A), selection(TEAM_A)]
    team_b_xi = [selection(TEAM_B), selection(TEAM_B)]
    innings = SimpleNamespace(
        innings_number=1,
        striker_id=team_a_xi[0].player_id,
        non_striker_id=team_a_xi[1].player_id,
        current_bowler_id=team_b_xi[0].player_id,
    )
    match = make_match(
        toss_winner_id=TEAM_A,
        toss_decision=TossDecision.BAT,
        players=team_a_xi + team_b_xi,
        innings=[innings],
    )

    readiness = _readiness(match)

    assert readiness.ready
    assert readiness.missing == []


def test_playing_team_count_must_match_players_per_side() -> None:
    match = make_match(players=[selection(TEAM_A)], players_per_side=2)

    readiness = _readiness(match)

    assert not readiness.team_a_players_complete
    assert "team_a_playing_team" in readiness.missing


def test_match_teams_must_differ() -> None:
    with pytest.raises(PydanticValidationError):
        MatchCreate(team_a_id=TEAM_A, team_b_id=TEAM_A)


def test_match_can_be_created_without_venue() -> None:
    payload = MatchCreate(team_a_id=TEAM_A, team_b_id=TEAM_B)

    assert payload.venue_id is None
    assert payload.total_overs is None


def test_playing_team_rejects_duplicate_players() -> None:
    player_id = uuid4()

    with pytest.raises(PydanticValidationError):
        PlayingTeamSetup(
            players=[
                PlayingTeamPlayer(player_id=player_id, batting_order=1),
                PlayingTeamPlayer(player_id=player_id, batting_order=2),
            ]
        )


def test_playing_team_batting_order_must_be_complete() -> None:
    with pytest.raises(PydanticValidationError):
        PlayingTeamSetup(
            players=[
                PlayingTeamPlayer(player_id=uuid4(), batting_order=1),
                PlayingTeamPlayer(player_id=uuid4(), batting_order=3),
            ]
        )


def test_openers_must_be_different() -> None:
    player_id = uuid4()

    with pytest.raises(PydanticValidationError):
        OpeningInningsSetup(
            striker_id=player_id,
            non_striker_id=player_id,
            opening_bowler_id=uuid4(),
        )
