"""Stage 11 completion: rule settings, eligibility, text safety and uploads."""

from datetime import date
from types import SimpleNamespace
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions import (
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.domain.bowling import bowler_ball_quota
from app.domain.tournament_eligibility import (
    age_on,
    eligibility_reference_date,
    is_overseas,
    overseas_count,
    player_eligibility_errors,
)
from app.domain.tournament_rules import (
    EligibilityPolicy,
    TournamentRules,
    bowler_quota_overs,
    disallowed_extras,
    scoring_capability_errors,
)
from app.models.enums import MatchType
from app.schemas.players import PlayerCreate
from app.schemas.tournaments import (
    CompetitionConfigUpdate,
    PointDeductionCreate,
    TournamentCreate,
    TournamentSeriesCreate,
)
from app.services.storage import LocalObjectStorage
from app.services.tournament_assets import detect_image_type, validate_image_upload
from app.utils.text import (
    sanitize_plain_text,
    validate_email,
    validate_http_url,
    validate_phone,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


# Rule settings


def test_new_rule_settings_default_to_engine_behaviour() -> None:
    rules = TournamentRules()

    assert rules.bowler_quota_policy == "engine_default"
    assert rules.overs_per_bowler is None
    assert rules.permitted_extras == ["wide", "no_ball", "bye", "leg_bye"]
    assert rules.eligibility.sex == "open"
    assert rules.standings_policy.partial_overs == "ball_fraction"
    assert scoring_capability_errors(rules) == []


def test_rule_versions_saved_before_these_settings_still_load() -> None:
    legacy = TournamentRules().model_dump(mode="json")
    for key in ("overs_per_bowler", "permitted_extras", "eligibility", "standings_policy"):
        legacy.pop(key)

    rules = TournamentRules.model_validate(legacy)

    assert rules.eligibility == EligibilityPolicy()


def test_fixed_bowler_quota_is_supported_and_validated() -> None:
    rules = TournamentRules(bowler_quota_policy="fixed", overs_per_bowler=5)

    assert scoring_capability_errors(rules) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"bowler_quota_policy": "fixed"},
        {"bowler_quota_policy": "engine_default", "overs_per_bowler": 4},
        {"bowler_quota_policy": "fixed", "overs_per_bowler": 25},
        # 11 bowlers x 1 over cannot complete 20 overs.
        {"bowler_quota_policy": "fixed", "overs_per_bowler": 1},
        {"permitted_extras": ["wide", "wide"]},
        {"permitted_extras": ["penalty"]},
        {"allowed_outcomes": ["tie"]},
        {"allowed_outcomes": ["win", "walkover"]},
        {"powerplay_segments": [{"from_over": 6, "to_over": 1}]},
        {"powerplay_segments": [{"from_over": 1, "to_over": 6}, {"from_over": 5, "to_over": 8}]},
        {"powerplay_segments": [{"from_over": 15, "to_over": 21}]},
        {"powerplay_segments": [{"from_over": None, "to_over": 6}]},
        {"overseas_player_limit": 4},
        {"overseas_player_limit": 12, "eligibility": {"home_nationality": "Pakistan"}},
        {"eligibility": {"minimum_age": 19, "maximum_age": 15}},
        {"eligibility": {"sex": "mixed"}},
        {"standings_policy": {"partial_overs": "cricket_notation"}},
    ],
)
def test_invalid_new_rule_settings_are_rejected(payload: dict) -> None:
    with pytest.raises(PydanticValidationError):
        TournamentRules.model_validate(payload)


def test_overseas_limit_with_home_nationality_is_activatable() -> None:
    rules = TournamentRules(
        overseas_player_limit=4,
        eligibility={"home_nationality": " Pakistan "},
    )

    assert rules.eligibility.home_nationality == "Pakistan"
    assert scoring_capability_errors(rules) == []


def test_powerplays_are_typed_but_still_blocked_from_activation() -> None:
    rules = TournamentRules(powerplay_segments=[{"from_over": 1, "to_over": 6}])

    assert rules.powerplay_segments[0].to_over == 6
    assert any("Powerplay" in item for item in scoring_capability_errors(rules))


def test_bowler_quota_follows_the_match_rule_snapshot() -> None:
    assert bowler_quota_overs(None, 20) == 4
    assert bowler_quota_overs({"bowler_quota_policy": "engine_default"}, 22) == 5
    assert bowler_quota_overs({"bowler_quota_policy": "fixed", "overs_per_bowler": 2}, 20) == 2
    assert bowler_quota_overs({"bowler_quota_policy": "unlimited"}, 5) is None


def _match(**values) -> SimpleNamespace:
    base = {"match_type": MatchType.T20, "total_overs": 20, "balls_per_over": 6}
    base.update(values)
    return SimpleNamespace(**base)


def test_bowler_ball_quota_without_snapshot_is_unchanged() -> None:
    assert bowler_ball_quota(_match()) == 24
    assert bowler_ball_quota(_match(effective_rules=None)) == 24


def test_bowler_ball_quota_uses_locked_tournament_rules() -> None:
    fixed = _match(effective_rules={"bowler_quota_policy": "fixed", "overs_per_bowler": 3})
    unlimited = _match(total_overs=5, effective_rules={"bowler_quota_policy": "unlimited"})

    assert bowler_ball_quota(fixed) == 18
    assert bowler_ball_quota(unlimited) is None


def test_disallowed_extras_only_apply_to_snapshotted_matches() -> None:
    assert disallowed_extras(None, wide=True, no_ball=True, bye=True, leg_bye=True) == []

    snapshot = {"permitted_extras": ["no_ball", "bye"]}
    assert disallowed_extras(snapshot, wide=True, no_ball=True, bye=False, leg_bye=True) == [
        "wide",
        "leg_bye",
    ]
    assert disallowed_extras(snapshot, wide=False, no_ball=True, bye=True, leg_bye=False) == []


# Eligibility


def test_age_counts_completed_years() -> None:
    assert age_on(date(2007, 6, 15), date(2026, 6, 14)) == 18
    assert age_on(date(2007, 6, 15), date(2026, 6, 15)) == 19
    assert age_on(date(2008, 2, 29), date(2026, 2, 28)) == 17


def _errors(policy: EligibilityPolicy, **player) -> list[str]:
    values = {
        "label": "Ali",
        "date_of_birth": date(2008, 1, 1),
        "sex": "male",
        "nationality": "Pakistan",
        "policy": policy,
        "reference_date": date(2026, 11, 1),
        "overseas_limit_active": False,
    }
    values.update(player)
    return player_eligibility_errors(**values)


def test_open_policy_accepts_any_player() -> None:
    assert _errors(EligibilityPolicy(), date_of_birth=None, sex=None, nationality=None) == []


def test_age_limits_are_enforced_and_need_a_date_of_birth() -> None:
    u19 = EligibilityPolicy(maximum_age=19)

    assert _errors(u19) == []
    assert _errors(u19, date_of_birth=date(2000, 1, 1))
    assert any("date of birth" in item for item in _errors(u19, date_of_birth=None))
    assert _errors(EligibilityPolicy(minimum_age=21))


def test_sex_restriction_needs_a_matching_recorded_sex() -> None:
    womens = EligibilityPolicy(sex="female")

    assert _errors(womens, sex="female") == []
    assert _errors(womens, sex="male")
    assert any("no recorded sex" in item for item in _errors(womens, sex=None))


def test_overseas_limit_needs_a_nationality() -> None:
    assert _errors(EligibilityPolicy(), nationality=None, overseas_limit_active=True)
    assert _errors(EligibilityPolicy(), overseas_limit_active=True) == []


def test_overseas_counting_ignores_case_and_spacing() -> None:
    assert not is_overseas(" pakistan ", "Pakistan")
    assert is_overseas("England", "Pakistan")
    assert overseas_count(["Pakistan", "England", "AUSTRALIA", None], "Pakistan") == 2


def test_age_reference_date_precedence() -> None:
    today = date(2026, 10, 14)
    start = date(2026, 12, 1)
    fixed = date(2026, 9, 1)

    assert eligibility_reference_date(EligibilityPolicy(age_reference_date=fixed), start, today) == fixed
    assert eligibility_reference_date(EligibilityPolicy(), start, today) == start
    assert eligibility_reference_date(EligibilityPolicy(), None, today) == today


def test_player_sex_is_optional_and_validated() -> None:
    assert PlayerCreate(full_name="A").sex is None
    assert PlayerCreate(full_name="A", sex="female").sex.value == "female"

    with pytest.raises(PydanticValidationError):
        PlayerCreate(full_name="A", sex="unknown")


# Text safety


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Plain text", "Plain text"),
        ("<b>Bold</b> & <i>italic</i>", "Bold & italic"),
        ("Hi<script>alert(1)</script> there", "Hi there"),
        ('<img src=x onerror="alert(1)">Logo', "Logo"),
        ("Score < 100 and > 50", "Score < 100 and > 50"),
        ("Line one<br>Line two", "Line one\nLine two"),
        ("Bell\x07 and null\x00 removed", "Bell and null removed"),
        ("   ", None),
        ("a\n\n\n\nb", "a\n\nb"),
    ],
)
def test_sanitize_plain_text(raw: str, expected: str | None) -> None:
    assert sanitize_plain_text(raw) == expected


def test_descriptions_and_terms_are_sanitized_by_schemas() -> None:
    created = TournamentCreate(name="Cup", description="<p>Welcome</p><script>x()</script>")
    config = CompetitionConfigUpdate(terms="<a href='javascript:x'>Rules</a>")
    series = TournamentSeriesCreate(name="Cup", description="<b>Annual</b>")

    assert created.description == "Welcome"
    assert config.terms == "Rules"
    assert series.description == "Annual"


@pytest.mark.parametrize("url", ["https://example.org", "http://club.pk/cup?year=2026"])
def test_http_urls_are_accepted(url: str) -> None:
    assert validate_http_url(url) == url


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "www.example.org", "ftp://example.org", "https://", "https://a b.com"],
)
def test_unsafe_or_relative_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_http_url(url)


def test_contact_email_and_phone_formats() -> None:
    assert validate_email("ops@club.pk") == "ops@club.pk"
    assert validate_phone("+92 (300) 123-4567") == "+92 (300) 123-4567"

    for bad in ("ops@", "ops club.pk", "<x>@a.com"):
        with pytest.raises(ValueError):
            validate_email(bad)

    with pytest.raises(ValueError):
        validate_phone("call me")


def test_configuration_update_validates_contact_formats() -> None:
    with pytest.raises(PydanticValidationError):
        CompetitionConfigUpdate(website="javascript:alert(1)")

    with pytest.raises(PydanticValidationError):
        CompetitionConfigUpdate(contact_email="not-an-email")

    assert CompetitionConfigUpdate(website="").website is None


def test_point_deduction_requires_points_and_reason() -> None:
    with pytest.raises(PydanticValidationError):
        PointDeductionCreate(tournament_team_id="00000000-0000-0000-0000-000000000001", points=0, reason="Slow over rate")

    with pytest.raises(PydanticValidationError):
        PointDeductionCreate(tournament_team_id="00000000-0000-0000-0000-000000000001", points=2, reason="  ")


# Uploads


def test_image_types_come_from_file_signatures() -> None:
    assert detect_image_type(PNG) == "image/png"
    assert detect_image_type(JPEG) == "image/jpeg"
    assert detect_image_type(WEBP) == "image/webp"
    assert detect_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert detect_image_type(b"GIF89a") is None


def test_upload_validation_rejects_bad_files() -> None:
    assert validate_image_upload(PNG, "image/png", 1024) == "image/png"
    assert validate_image_upload(JPEG, None, 1024) == "image/jpeg"
    assert validate_image_upload(WEBP, "application/octet-stream", 1024) == "image/webp"

    with pytest.raises(ValidationError):
        validate_image_upload(b"", "image/png", 1024)

    with pytest.raises(PayloadTooLargeError):
        validate_image_upload(PNG + b"\x00" * 2000, "image/png", 1024)

    with pytest.raises(UnsupportedMediaTypeError):
        validate_image_upload(b"<svg/>", "image/svg+xml", 1024)

    # A PNG renamed or labelled as JPEG is refused.
    with pytest.raises(UnsupportedMediaTypeError):
        validate_image_upload(PNG, "image/jpeg", 1024)


def test_storage_writes_atomically_and_stays_inside_its_root(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path)
    storage.put("tournaments/t1/logo-abc.png", PNG)

    assert storage.exists("tournaments/t1/logo-abc.png")
    assert storage.path_for("tournaments/t1/logo-abc.png").read_bytes() == PNG
    assert not list((tmp_path / "tournaments" / "t1").glob(".upload-*"))

    for key in ("../escape.png", "/etc/passwd", "tournaments/../../x.png", ""):
        with pytest.raises(ValueError):
            storage.path_for(key)


def test_match_reports_permitted_extras_for_the_scoring_screen() -> None:
    from app.services.match_setup.presenters import permitted_extras

    assert permitted_extras(SimpleNamespace(effective_rules=None)) == ["wide", "no_ball", "bye", "leg_bye"]
    assert permitted_extras(SimpleNamespace(effective_rules={"permitted_extras": ["no_ball"]})) == ["no_ball"]
    # Snapshots locked before the setting existed allow every extra.
    assert permitted_extras(SimpleNamespace(effective_rules={"overs_per_innings": 20})) == [
        "wide",
        "no_ball",
        "bye",
        "leg_bye",
    ]
