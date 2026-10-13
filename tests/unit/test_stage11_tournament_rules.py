from datetime import datetime
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions import ValidationError
from app.domain.tournament_rules import (
    FORMAT_PRESETS,
    TournamentRules,
    checksum_rules,
    match_config_from_rules,
    match_config_mismatches,
    rules_preset,
    scoring_capability_errors,
    validate_for_activation,
)
from app.schemas.tournaments import (
    CompetitionConfig,
    CompetitionConfigUpdate,
    RuleVersionCreate,
    TransitionRequest,
)
from app.services.tournaments import validate_rules_payload


def test_default_rules_are_activatable() -> None:
    rules = TournamentRules()

    assert rules.allowed_outcomes == ["win", "tie"]
    assert scoring_capability_errors(rules) == []
    validate_for_activation(rules)


@pytest.mark.parametrize("format_code", sorted(FORMAT_PRESETS))
def test_presets_never_enable_unsupported_options(format_code: str) -> None:
    rules = rules_preset(format_code)

    assert rules.format_code == format_code
    assert not rules.super_over_enabled
    assert not rules.dls_enabled
    assert not rules.impact_player_enabled
    assert rules.minimum_players_to_start == rules.players_per_side


@pytest.mark.parametrize("format_code", ["hundred", "indoor"])
def test_special_formats_are_blocked_for_activation(format_code: str) -> None:
    with pytest.raises(ValidationError):
        validate_for_activation(rules_preset(format_code))


@pytest.mark.parametrize(
    "overrides",
    [
        {"super_over_enabled": True},
        {"dls_enabled": True},
        {"impact_player_enabled": True},
        {"reduced_overs_enabled": True},
        {"allow_match_overrides": True},
        {"overseas_player_limit": 4},
        {"best_of_finals": 3},
        {"allowed_outcomes": ["win", "tie", "no_result"]},
        {"balls_per_over": 8},
        {"innings_per_team": 2},
        {"powerplay_segments": [{"from_over": 1, "to_over": 6}]},
    ],
)
def test_forbidden_rule_configurations_report_errors(overrides: dict) -> None:
    rules = TournamentRules(**overrides)

    result = validate_rules_payload(rules)

    assert result["valid"] is False
    assert result["errors"]


def test_bonus_points_are_rejected() -> None:
    rules = TournamentRules.model_validate({"points": {"bonus_points_enabled": True}})

    assert any("Bonus" in item for item in scoring_capability_errors(rules))


@pytest.mark.parametrize(
    "payload",
    [
        {"players_per_side": 11, "minimum_players_to_start": 12},
        {"minimum_roster_size": 15, "maximum_roster_size": 12},
        {"players_per_side": 11, "minimum_roster_size": 10},
        {"tie_breakers": ["points", "points"]},
        {"tie_breakers": ["drawing_of_lots", "points"]},
        {"best_of_finals": 2},
        {"structure": "groups_knockout"},
        {"unknown_field": True},
    ],
)
def test_inconsistent_rules_are_rejected(payload: dict) -> None:
    with pytest.raises(PydanticValidationError):
        TournamentRules.model_validate(payload)


def test_groups_knockout_with_group_size_is_valid() -> None:
    rules = TournamentRules(structure="groups_knockout", teams_per_group=4)

    assert rules.teams_per_group == 4


def test_checksum_is_stable_and_content_sensitive() -> None:
    first = TournamentRules()
    same = TournamentRules.model_validate(first.model_dump(mode="json"))
    changed = TournamentRules(overs_per_innings=10)

    assert checksum_rules(first) == checksum_rules(same)
    assert checksum_rules(first) != checksum_rules(changed)
    assert len(checksum_rules(first)) == 64


def test_match_config_follows_rules() -> None:
    rules = TournamentRules(
        overs_per_innings=10,
        players_per_side=8,
        minimum_players_to_start=8,
        minimum_roster_size=8,
    )

    assert match_config_from_rules(rules) == {
        "players_per_side": 8,
        "total_overs": 10,
        "balls_per_over": 6,
        "innings_per_team": 1,
    }
    assert match_config_mismatches(rules, match_config_from_rules(rules)) == []
    assert match_config_mismatches(
        rules,
        {**match_config_from_rules(rules), "total_overs": 20},
    ) == ["total_overs must be 10 for this tournament"]


def test_rule_version_create_forbids_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        RuleVersionCreate.model_validate({"rules": {}, "version": 4})


def test_configuration_update_requires_a_field() -> None:
    with pytest.raises(PydanticValidationError):
        CompetitionConfigUpdate.model_validate({})


def test_configuration_update_requires_timezone_aware_times() -> None:
    with pytest.raises(PydanticValidationError):
        CompetitionConfigUpdate(registration_opens_at=datetime(2026, 11, 1, 9, 0))


def test_configuration_update_is_partial() -> None:
    payload = CompetitionConfigUpdate(maximum_teams=8)

    assert payload.model_dump(exclude_unset=True) == {"maximum_teams": 8}


@pytest.mark.parametrize(
    "payload",
    [
        {"minimum_teams": 6, "maximum_teams": 4},
        {"minimum_teams": 4, "maximum_teams": 8, "expected_teams": 10},
        {"timezone": "Mars/Olympus"},
        {"registration_mode": "secret"},
        {
            "registration_opens_at": "2026-11-02T00:00:00+00:00",
            "registration_closes_at": "2026-11-01T00:00:00+00:00",
        },
    ],
)
def test_merged_configuration_rejects_invalid_combinations(payload: dict) -> None:
    with pytest.raises(PydanticValidationError):
        CompetitionConfig.model_validate(payload)


def test_large_and_two_team_capacities_are_valid() -> None:
    CompetitionConfig(minimum_teams=2, maximum_teams=2)
    CompetitionConfig(minimum_teams=2, maximum_teams=512, expected_teams=301)


def test_transition_request_requires_known_status() -> None:
    assert TransitionRequest(target_status="scheduled").target_status.value == "scheduled"

    with pytest.raises(PydanticValidationError):
        TransitionRequest(target_status="finished")
