from uuid import uuid4
from app.services.match_setup.tournament_snapshot import lineup_roster_errors


def test_lineup_from_roster_is_valid() -> None:
    roster = {uuid4() for _ in range(4)}

    assert lineup_roster_errors(
        team_label="Team A",
        selected_ids=list(roster)[:2],
        roster_ids=roster,
        captain_count=1,
    ) == []


def test_lineup_rejects_players_outside_roster() -> None:
    roster = {uuid4(), uuid4()}
    outsider = uuid4()

    errors = lineup_roster_errors(
        team_label="Team A",
        selected_ids=[next(iter(roster)), outsider],
        roster_ids=roster,
        captain_count=0,
    )

    assert len(errors) == 1
    assert str(outsider) in errors[0]


def test_unavailable_players_are_treated_as_outside_roster() -> None:
    # The roster query only returns available players, so an injured
    # player is simply absent from roster_ids.
    available = uuid4()
    injured = uuid4()

    errors = lineup_roster_errors(
        team_label="Team B",
        selected_ids=[available, injured],
        roster_ids={available},
        captain_count=0,
    )

    assert errors and str(injured) in errors[0]


def test_lineup_rejects_multiple_captains() -> None:
    roster = {uuid4(), uuid4()}

    errors = lineup_roster_errors(
        team_label="Team A",
        selected_ids=roster,
        roster_ids=roster,
        captain_count=2,
    )

    assert errors == ["Team A playing team has more than one captain"]
