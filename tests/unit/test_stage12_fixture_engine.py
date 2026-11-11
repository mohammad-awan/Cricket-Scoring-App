import pytest
from app.domain.fixture_engine import (
    FixtureError,
    Pairing,
    fixture_summary,
    knockout_bracket,
    random_round_robin,
    round_robin,
    validate_manual,
)


@pytest.mark.parametrize("count", range(2, 17))
def test_single_round_robin_match_count(count):
    teams = [str(i) for i in range(count)]
    fixtures = round_robin(teams)
    summary = fixture_summary(fixtures)
    assert summary["matches"] == count * (count - 1) // 2


@pytest.mark.parametrize("count", range(2, 17))
def test_double_round_robin_match_count(count):
    teams = [str(i) for i in range(count)]
    fixtures = round_robin(teams, legs=2)
    summary = fixture_summary(fixtures)
    assert summary["matches"] == count * (count - 1)


@pytest.mark.parametrize("count", [3, 5, 7, 9])
def test_odd_teams_have_one_bye_per_round(count):
    teams = [str(i) for i in range(count)]
    fixtures = round_robin(teams)
    byes = [item for item in fixtures if item.is_bye]
    assert len(byes) == count
    assert len({item.round_number for item in byes}) == count


def test_no_team_plays_itself():
    fixtures = round_robin(["A", "B", "C", "D", "E"])

    for item in fixtures:
        if not item.is_bye:
            assert item.home_team_id != item.away_team_id


def test_no_team_plays_twice_in_same_round():
    fixtures = round_robin(["A", "B", "C", "D", "E", "F"])

    for round_number in range(1, 6):
        participants = []

        for item in fixtures:
            if item.round_number == round_number:
                if item.home_team_id is not None:
                    participants.append(item.home_team_id)
                if item.away_team_id is not None:
                    participants.append(item.away_team_id)

        assert len(participants) == len(set(participants))


def test_random_draw_is_reproducible():
    teams = ["A", "B", "C", "D", "E", "F"]
    first = random_round_robin(teams, seed=2026)
    second = random_round_robin(teams, seed=2026)
    assert first == second


def test_manual_draw_rejects_self_opponent():
    with pytest.raises(FixtureError):
        validate_manual([Pairing(1, "A", "A")], allowed_team_ids=["A", "B"])


def test_manual_draw_accepts_complete_pairings():
    fixtures = [
        Pairing(1, "A", "B"),
        Pairing(2, "A", "C"),
        Pairing(3, "B", "C"),
    ]
    validate_manual(fixtures, allowed_team_ids=["A", "B", "C"])


def test_manual_draw_rejects_missing_pairings():
    with pytest.raises(FixtureError):
        validate_manual([Pairing(1, "A", "B")], allowed_team_ids=["A", "B", "C"])


@pytest.mark.parametrize("count", range(2, 17))
def test_knockout_match_count(count):
    teams = [str(i) for i in range(count)]
    slots = knockout_bracket(teams)
    assert len(slots) == count - 1
    assert len({slot.match_number for slot in slots}) == len(slots)


def test_knockout_is_deterministic():
    teams = ["A", "B", "C", "D", "E"]
    assert knockout_bracket(teams, seed=123) == knockout_bracket(teams, seed=123)


def test_duplicate_team_ids_are_rejected():
    with pytest.raises(FixtureError):
        round_robin(["A", "A", "B"])
