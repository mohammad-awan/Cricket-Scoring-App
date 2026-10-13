from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from app.core.exceptions import ConflictError
from app.models import TournamentStatus
from app.services.tournaments import (
    CONFIGURATION_LOCKED_STATUSES,
    LEGACY_STATUSES,
    TOURNAMENT_TRANSITIONS,
    capacity_errors,
    ensure_configuration_editable,
    ensure_not_final,
    ensure_roster_editable,
    ensure_transition_allowed,
    transition_allowed,
)


def test_every_status_has_a_transition_entry() -> None:
    assert set(TOURNAMENT_TRANSITIONS) == set(TournamentStatus)


def test_archived_is_terminal() -> None:
    assert TOURNAMENT_TRANSITIONS[TournamentStatus.ARCHIVED] == set()


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TournamentStatus.DRAFT, TournamentStatus.REGISTRATION_OPEN),
        (TournamentStatus.REGISTRATION_OPEN, TournamentStatus.REGISTRATION_CLOSED),
        (TournamentStatus.REGISTRATION_CLOSED, TournamentStatus.REGISTRATION_OPEN),
        (TournamentStatus.REGISTRATION_CLOSED, TournamentStatus.SCHEDULED),
        (TournamentStatus.SCHEDULED, TournamentStatus.LIVE),
        (TournamentStatus.LIVE, TournamentStatus.COMPLETED),
        (TournamentStatus.LIVE, TournamentStatus.SUSPENDED),
        (TournamentStatus.SUSPENDED, TournamentStatus.LIVE),
        (TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED),
        (TournamentStatus.CANCELLED, TournamentStatus.ARCHIVED),
        (TournamentStatus.ACTIVE, TournamentStatus.SCHEDULED),
    ],
)
def test_allowed_transitions(current: TournamentStatus, target: TournamentStatus) -> None:
    assert transition_allowed(current, target)
    ensure_transition_allowed(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TournamentStatus.DRAFT, TournamentStatus.LIVE),
        (TournamentStatus.DRAFT, TournamentStatus.ARCHIVED),
        (TournamentStatus.REGISTRATION_OPEN, TournamentStatus.SCHEDULED),
        (TournamentStatus.SCHEDULED, TournamentStatus.REGISTRATION_OPEN),
        (TournamentStatus.LIVE, TournamentStatus.CANCELLED),
        (TournamentStatus.LIVE, TournamentStatus.ARCHIVED),
        (TournamentStatus.COMPLETED, TournamentStatus.LIVE),
        (TournamentStatus.ARCHIVED, TournamentStatus.DRAFT),
    ],
)
def test_forbidden_transitions(current: TournamentStatus, target: TournamentStatus) -> None:
    assert not transition_allowed(current, target)

    with pytest.raises(ConflictError):
        ensure_transition_allowed(current, target)


def test_legacy_statuses_cover_pre_stage11_values() -> None:
    assert LEGACY_STATUSES == {
        TournamentStatus.DRAFT,
        TournamentStatus.ACTIVE,
        TournamentStatus.COMPLETED,
    }


def _tournament(status: TournamentStatus, roster_lock_at=None):
    return SimpleNamespace(status=status, roster_lock_at=roster_lock_at)


@pytest.mark.parametrize("status", sorted(CONFIGURATION_LOCKED_STATUSES))
def test_configuration_locks_once_scheduled(status: TournamentStatus) -> None:
    with pytest.raises(ConflictError):
        ensure_configuration_editable(_tournament(status))


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.DRAFT,
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.SUSPENDED,
    ],
)
def test_configuration_editable_before_scheduling(status: TournamentStatus) -> None:
    ensure_configuration_editable(_tournament(status))
    ensure_roster_editable(_tournament(status))


def test_roster_lock_deadline_blocks_edits() -> None:
    past = datetime.now(UTC) - timedelta(minutes=1)
    future = datetime.now(UTC) + timedelta(days=1)

    ensure_roster_editable(_tournament(TournamentStatus.REGISTRATION_OPEN, future))

    with pytest.raises(ConflictError):
        ensure_roster_editable(_tournament(TournamentStatus.REGISTRATION_OPEN, past))


def test_final_statuses_block_changes() -> None:
    ensure_not_final(_tournament(TournamentStatus.LIVE))

    for status in (
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    ):
        with pytest.raises(ConflictError):
            ensure_not_final(_tournament(status))


def test_capacity_cannot_drop_below_existing_registrations() -> None:
    assert capacity_errors(
        maximum_teams=8,
        reserve_team_limit=2,
        active_main=8,
        active_reserve=2,
    ) == []
    assert capacity_errors(
        maximum_teams=None,
        reserve_team_limit=0,
        active_main=300,
        active_reserve=0,
    ) == []

    errors = capacity_errors(
        maximum_teams=6,
        reserve_team_limit=1,
        active_main=7,
        active_reserve=2,
    )

    assert len(errors) == 2
