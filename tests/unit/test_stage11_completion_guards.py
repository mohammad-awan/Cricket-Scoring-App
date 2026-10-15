from types import SimpleNamespace
import pytest
from app.api.dependencies import require_organizer
from app.core.exceptions import ConflictError, ValidationError
from app.domain.tournament_rules import TournamentRules, validate_for_activation
from app.models.enums import TournamentStatus
from app.services.tournaments import validate_tournament_identity_update


def tournament_stub(status: TournamentStatus) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        name="National Crickter League",
        slug="national-cricket-league",
        season="2026",
        start_date=None,
        end_date=None
    )


def test_tournament_operations_need_no_token():
    assert require_organizer() is None


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.DRAFT,
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
    ],
)
def test_identity_editable_before_scheduling(status):
    tournament = tournament_stub(status)

    validate_tournament_identity_update(
        tournament,
        {"name": "National League"}
    )


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
        TournamentStatus.SUSPENDED,
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    ],
)
def test_identity_locked_after_scheduling(status):
    tournament = tournament_stub(status)

    with pytest.raises(ConflictError):
        validate_tournament_identity_update(
            tournament,
            {"name": "Change Tournament"}
        )


def test_same_identity_value_is_not_a_change():
    tournament = tournament_stub(TournamentStatus.SCHEDULED)

    validate_tournament_identity_update(
        tournament,
        {"name": tournament.name}
    )

@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
        TournamentStatus.SUSPENDED,
    ],
)
def test_description_remains_editable(status):
    tournament = tournament_stub(status)

    validate_tournament_identity_update(
        tournament,
        {"description": "New Description"}
    )


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    ],
)
def test_terminal_tournament_is_read_only(status):
    tournament = tournament_stub(status)

    with pytest.raises(ConflictError):
        validate_tournament_identity_update(
            tournament,
            {"description": "Changed"}
        )


def test_standard_t20_activation():
    rules = TournamentRules()
    validate_for_activation(rules)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mandatory_break_minutes", 15),
        ("innings_time_minutes", 90),
        ("timeout_minutes", 5),
    ],
)
def test_unsupported_time_rules_are_rejected(field, value):
    rules = TournamentRules(**{field: value})

    with pytest.raises(ValidationError):
        validate_for_activation(rules)
