
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.schemas.fixtures import (
    FixtureCreate,
    FixtureUpdateRequest,
    FixtureGenerationRequest,
    BracketDependencyCreate,
    VenueAvailabilityCreate,
    SchedulingConstraintCreate,
    FixturePublishRequest,
    FixtureScheduleRequest,
)


def utc_now():
    return datetime.now(timezone.utc)


def valid_fixture_data():
    start = utc_now()

    return {
        "tournament_id": uuid4(),
        "generation_run_id": uuid4(),
        "round_id": uuid4(),
        "fixture_number": 1,
        "home_team_id": uuid4(),
        "away_team_id": uuid4(),
        "scheduled_at": start,
        "ends_at": start + timedelta(hours=2),
    }


# ---------------------------------------
# FIXTURE GENERATION
# ---------------------------------------

def test_generation_request_valid():
    request = FixtureGenerationRequest(
        tournament_id=uuid4(),
        method="round_robin",
    )

    assert request.method == "round_robin"
    assert request.configuration == {}


def test_generation_rejects_invalid_method():
    with pytest.raises(ValidationError):
        FixtureGenerationRequest(
            tournament_id=uuid4(),
            method="invalid_method",
        )


def test_generation_rejects_extra_fields():
    with pytest.raises(ValidationError):
        FixtureGenerationRequest(
            tournament_id=uuid4(),
            method="knockout",
            unknown_field="not_allowed",
        )


def test_generation_configuration_is_independent():
    first = FixtureGenerationRequest(
        tournament_id=uuid4(),
        method="manual",
    )

    second = FixtureGenerationRequest(
        tournament_id=uuid4(),
        method="manual",
    )

    first.configuration["example"] = True

    assert second.configuration == {}


# ---------------------------------------
# FIXTURE CREATION
# ---------------------------------------

def test_create_fixture_valid():
    fixture = FixtureCreate(**valid_fixture_data())

    assert fixture.fixture_number == 1
    assert fixture.home_team_id != fixture.away_team_id


def test_create_fixture_allows_unresolved_teams():
    data = valid_fixture_data()
    data["home_team_id"] = None
    data["away_team_id"] = None

    fixture = FixtureCreate(**data)

    assert fixture.home_team_id is None
    assert fixture.away_team_id is None


def test_create_fixture_rejects_same_teams():
    data = valid_fixture_data()
    data["away_team_id"] = data["home_team_id"]

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


def test_create_fixture_rejects_invalid_number():
    data = valid_fixture_data()
    data["fixture_number"] = 0

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


def test_create_fixture_rejects_reverse_time():
    data = valid_fixture_data()

    data["ends_at"] = (
        data["scheduled_at"] - timedelta(minutes=1)
    )

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


def test_create_fixture_rejects_equal_times():
    data = valid_fixture_data()
    data["ends_at"] = data["scheduled_at"]

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


def test_create_fixture_rejects_invalid_uuid():
    data = valid_fixture_data()
    data["tournament_id"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


def test_create_fixture_rejects_naive_datetime():
    data = valid_fixture_data()

    data["scheduled_at"] = datetime.now()
    data["ends_at"] = (
        data["scheduled_at"] + timedelta(hours=2)
    )

    with pytest.raises(ValidationError):
        FixtureCreate(**data)


# ---------------------------------------
# FIXTURE UPDATE
# ---------------------------------------

def test_update_fixture_valid():
    update = FixtureUpdateRequest(
        expected_version=1,
        notes="Updated fixture",
    )

    assert update.expected_version == 1
    assert update.notes == "Updated fixture"


def test_update_rejects_invalid_version():
    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            expected_version=0,
            notes="Updated fixture",
        )


def test_update_requires_version():
    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            notes="Missing version",
        )


def test_update_requires_changes():
    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            expected_version=1,
        )


def test_update_rejects_extra_fields():
    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            expected_version=1,
            status="completed",
        )


def test_update_rejects_same_teams():
    team_id = uuid4()

    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            expected_version=1,
            home_team_id=team_id,
            away_team_id=team_id,
        )


def test_update_rejects_invalid_time_range():
    start = utc_now()

    with pytest.raises(ValidationError):
        FixtureUpdateRequest(
            expected_version=1,
            scheduled_at=start,
            ends_at=start - timedelta(hours=1),
        )


def test_update_allows_partial_changes():
    update = FixtureUpdateRequest(
        expected_version=2,
        notes="Match moved to another date",
    )

    changes = update.model_dump(
        exclude_unset=True,
        exclude={"expected_version"},
    )

    assert changes == {
        "notes": "Match moved to another date",
    }


# ---------------------------------------
# KNOCKOUT BRACKET
# ---------------------------------------

def test_bracket_dependency_valid():
    dependency = BracketDependencyCreate(
        fixture_id=uuid4(),
        source_fixture_id=uuid4(),
        target_side="home",
        advancement="winner",
    )

    assert dependency.target_side == "home"


def test_bracket_rejects_self_dependency():
    fixture_id = uuid4()

    with pytest.raises(ValidationError):
        BracketDependencyCreate(
            fixture_id=fixture_id,
            source_fixture_id=fixture_id,
            target_side="home",
        )


def test_bracket_rejects_invalid_side():
    with pytest.raises(ValidationError):
        BracketDependencyCreate(
            fixture_id=uuid4(),
            source_fixture_id=uuid4(),
            target_side="middle",
        )


def test_bracket_rejects_invalid_advancement():
    with pytest.raises(ValidationError):
        BracketDependencyCreate(
            fixture_id=uuid4(),
            source_fixture_id=uuid4(),
            target_side="away",
            advancement="random",
        )


# ---------------------------------------
# VENUE AVAILABILITY
# ---------------------------------------

def test_venue_availability_valid():
    start = utc_now()

    availability = VenueAvailabilityCreate(
        tournament_id=uuid4(),
        venue_id=uuid4(),
        start_at=start,
        end_at=start + timedelta(hours=3),
    )

    assert availability.is_available is True


def test_venue_rejects_invalid_time():
    start = utc_now()

    with pytest.raises(ValidationError):
        VenueAvailabilityCreate(
            tournament_id=uuid4(),
            venue_id=uuid4(),
            start_at=start,
            end_at=start,
        )


def test_venue_rejects_reverse_time():
    start = utc_now()

    with pytest.raises(ValidationError):
        VenueAvailabilityCreate(
            tournament_id=uuid4(),
            venue_id=uuid4(),
            start_at=start,
            end_at=start - timedelta(hours=1),
        )


# ---------------------------------------
# SCHEDULING CONSTRAINTS
# ---------------------------------------

def test_scheduling_constraint_valid():
    constraint = SchedulingConstraintCreate(
        tournament_id=uuid4(),
        name="minimum_rest",
        configuration={"minutes": 60},
    )

    assert constraint.configuration["minutes"] == 60


def test_scheduling_constraint_rejects_empty_name():
    with pytest.raises(ValidationError):
        SchedulingConstraintCreate(
            tournament_id=uuid4(),
            name="",
        )


# ---------------------------------------
# PUBLICATION
# ---------------------------------------

def test_publish_request_valid():
    request = FixturePublishRequest(
        expected_fixture_count=10,
    )

    assert request.expected_fixture_count == 10


def test_publish_rejects_zero_count():
    with pytest.raises(ValidationError):
        FixturePublishRequest(
            expected_fixture_count=0,
        )


def test_publish_requires_fixture_count():
    with pytest.raises(ValidationError):
        FixturePublishRequest()


def test_publish_rejects_extra_fields():
    with pytest.raises(ValidationError):
        FixturePublishRequest(
            generation_run_id=uuid4(),
            expected_fixture_count=10,
        )


# ---------------------------------------
# SCHEDULE GENERATION
# ---------------------------------------

def test_schedule_request_valid():
    request = FixtureScheduleRequest(
        tournament_id=uuid4(),
        generation_run_id=uuid4(),
        duration_minutes=120,
        minimum_rest_minutes=30,
    )

    assert request.duration_minutes == 120


def test_schedule_rejects_zero_duration():
    with pytest.raises(ValidationError):
        FixtureScheduleRequest(
            tournament_id=uuid4(),
            generation_run_id=uuid4(),
            duration_minutes=0,
        )


def test_schedule_rejects_negative_rest():
    with pytest.raises(ValidationError):
        FixtureScheduleRequest(
            tournament_id=uuid4(),
            generation_run_id=uuid4(),
            duration_minutes=120,
            minimum_rest_minutes=-10,
        )
