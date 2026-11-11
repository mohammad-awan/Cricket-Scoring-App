from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.fixture_engine import FixtureError
from app.domain.fixture_planning import analyze, make_plan
from app.models import Match, MatchStatus
from app.models.entities.fixtures import FixtureGenerationRun
from app.schemas.fixture_planning import FixturePlanRequest
from app.services.fixture import FixtureConflictError, FixtureValidationError
from app.services.fixture_planning import FixturePlanningService, validate_fixture_activation


def config(team_count=4, **overrides):
    values = dict(team_ids=[uuid4() for _ in range(team_count)], venue_ids=[uuid4(), uuid4()],
                  start_date=date(2026, 11, 12), end_date=date(2026, 12, 12), timezone="Asia/Karachi")
    values.update(overrides)
    return FixturePlanRequest(**values)


@pytest.mark.parametrize("count", range(2, 10))
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_preview_counts_and_byes(count, legs):
    request = config(count, legs=legs)
    result = make_plan(request, list(map(str, request.team_ids)))
    assert result["summary"]["matches"] == count * (count - 1) // 2 * legs
    assert all(value == (count - 1) * legs for value in result["summary"]["team_counts"].values())
    assert len(result["byes"]) == (count * legs if count % 2 else 0)
    assert result["valid"], result["violations"]


def test_random_preview_is_deterministic_without_writes():
    request = config(6, method="random", seed=2026)
    approved = list(map(str, request.team_ids))
    assert make_plan(request, approved) == make_plan(request, approved)
    other = request.model_copy(update={"seed": 73})
    assert make_plan(request, approved)["fixtures"] != make_plan(other, approved)["fixtures"]


@pytest.mark.parametrize("count", [2, 3, 4, 5, 7, 8, 9])
def test_knockout_has_n_minus_one_fixtures_and_only_earlier_dependencies(count):
    request = config(count, format="knockout")
    result = make_plan(request, list(map(str, request.team_ids)))
    assert len(result["fixtures"]) == count - 1
    assert result["valid"], result["violations"]
    by_number = {row["fixture_number"]: row for row in result["fixtures"]}
    for row in result["fixtures"]:
        for side in ("home", "away"):
            if row[f"{side}_source"]:
                parent = by_number[int(row[f"{side}_source"].split(":")[1])]
                assert parent["ends_at"] <= row["scheduled_at"]


def test_hybrid_crosses_group_winners_with_other_group_runners_up():
    request = config(8, format="hybrid", group_count=2)
    result = make_plan(request, list(map(str, request.team_ids)))
    assert result["valid"], result["violations"]
    assert result["summary"]["matches"] == 12 + 3
    semi = [row for row in result["fixtures"] if row["home_source"] and row["home_source"].startswith("group:")]
    assert {(row["home_source"], row["away_source"]) for row in semi} == {
        ("group:A:1", "group:B:2"), ("group:B:1", "group:A:2")}


def test_seed_pots_distribute_one_team_per_group_and_reject_duplicates():
    request = config(8, method="random", seed=42, format="groups", group_count=4)
    request.seed_pots = [request.team_ids[:4], request.team_ids[4:]]
    result = make_plan(request, list(map(str, request.team_ids)))
    for group in result["groups"].values():
        assert len(set(group) & set(map(str, request.team_ids[:4]))) == 1
    request.seed_pots[1][0] = request.team_ids[0]
    with pytest.raises(FixtureError, match="exactly once"):
        make_plan(request, list(map(str, request.team_ids)))


def test_capacity_failure_does_not_invent_dates():
    request = config(6, start_date=date(2026, 11, 12), end_date=date(2026, 11, 12), times=["10:00"], venue_ids=[uuid4()])
    result = make_plan(request, list(map(str, request.team_ids)))
    assert not result["valid"]
    assert any(item["code"] == "capacity" for item in result["violations"])
    assert result["summary"]["scheduled"] < result["summary"]["matches"]


def test_manual_incomplete_draw_is_an_invalid_but_saveable_preview():
    request = config(3, method="manual", auto_schedule=False)
    request.pairings = []
    result = make_plan(request, list(map(str, request.team_ids)))
    assert not result["valid"]
    assert any(item["code"] == "pairing" for item in result["violations"])


def test_manual_override_rechecks_team_and_venue_collisions():
    request = config()
    teams = list(map(str, request.team_ids))
    result = make_plan(request, teams)
    rows = deepcopy(result["fixtures"])
    rows[1].update(venue_id=rows[0]["venue_id"], scheduled_at=rows[0]["scheduled_at"], ends_at=rows[0]["ends_at"])
    report = analyze(rows, request, teams)
    assert not report["valid"]
    assert any("Venue collision" in item["message"] for item in report["violations"])


def test_local_weekdays_use_the_tournament_zone():
    request = config(2, weekdays=[0], times=["00:30"], start_date=date(2026, 11, 16), end_date=date(2026, 11, 16))
    result = make_plan(request, list(map(str, request.team_ids)))
    start = result["fixtures"][0]["scheduled_at"]
    assert start.weekday() == 0 and start.astimezone(timezone.utc).weekday() == 6
    assert result["valid"]


def test_daylight_saving_transition_preserves_elapsed_match_duration():
    request = config(2, timezone="America/New_York", start_date=date(2026, 11, 1), end_date=date(2026, 11, 1), times=["00:30"], duration_minutes=180)
    result = make_plan(request, list(map(str, request.team_ids)))
    row = result["fixtures"][0]
    assert row["ends_at"].astimezone(timezone.utc) - row["scheduled_at"].astimezone(timezone.utc) == timedelta(hours=3)
    assert result["valid"]


@pytest.mark.parametrize("values", [
    {"method": "random", "seed": None}, {"timezone": "Not/AZone"}, {"weekdays": []},
    {"times": ["25:00"]}, {"start_date": "2026-11-15", "end_date": "2026-11-12"},
])
def test_invalid_planning_inputs_are_rejected(values):
    with pytest.raises(ValidationError):
        config(**values)


def mock_service():
    session = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    service = FixturePlanningService(session)
    service.repo.scheduling_lock = AsyncMock()
    return service, session


async def test_publication_replay_does_not_create_duplicate_matches():
    service, session = mock_service()
    run = FixtureGenerationRun(id=uuid4(), status="published")
    fixture = SimpleNamespace(id=uuid4(), version=2)
    service.load = AsyncMock(return_value=(run, [fixture], []))
    service.create_match = AsyncMock()
    result = await service.publish(run.id, {fixture.id: 1}, "Retry publication")
    assert result["replayed"] and result["created_match_count"] == 0
    service.create_match.assert_not_awaited()
    session.add.assert_not_called()


async def test_publication_rejects_stale_versions_before_writing():
    service, session = mock_service()
    run = FixtureGenerationRun(id=uuid4(), status="draft")
    fixture = SimpleNamespace(id=uuid4(), version=3)
    service.load = AsyncMock(return_value=(run, [fixture], []))
    with pytest.raises(FixtureConflictError, match="changed"):
        await service.publish(run.id, {fixture.id: 2}, "Confirm")
    session.add.assert_not_called()


async def test_publication_rejects_conflicts_before_any_match_creation():
    service, session = mock_service()
    run = FixtureGenerationRun(id=uuid4(), tournament_id=uuid4(), status="draft")
    fixture = SimpleNamespace(id=uuid4(), version=1, status="draft")
    service.load = AsyncMock(return_value=(run, [fixture], []))
    service.configuration = AsyncMock(return_value=config())
    service.context = AsyncMock()
    service.report = AsyncMock(return_value={"valid": False, "violations": [{"message": "Venue collision"}]})
    service.create_match = AsyncMock()
    with pytest.raises(FixtureValidationError, match="Venue collision"):
        await service.publish(run.id, {fixture.id: 1}, "Confirm")
    service.create_match.assert_not_awaited()
    assert fixture.status == "draft"


async def test_publication_marks_fixtures_and_links_matches_before_caller_commit():
    service, session = mock_service()
    run = FixtureGenerationRun(id=uuid4(), tournament_id=uuid4(), status="draft")
    fixture = SimpleNamespace(id=uuid4(), version=1, status="draft", published_at=None)
    service.load = AsyncMock(return_value=(run, [fixture], []))
    service.configuration = AsyncMock(return_value=config())
    service.context = AsyncMock()
    service.report = AsyncMock(return_value={"valid": True})
    service.create_match = AsyncMock(return_value=True)
    result = await service.publish(run.id, {fixture.id: 1}, "Confirmed by organizer")
    assert result["created_match_count"] == 1
    assert run.status == fixture.status == "published"
    assert fixture.version == 2 and fixture.published_at is not None
    service.create_match.assert_awaited_once_with(fixture)
    session.commit.assert_not_called()


async def test_tie_does_not_advance_and_corrected_linked_match_is_flagged():
    service, session = mock_service()
    parent_id, target_id, team_id = uuid4(), uuid4(), uuid4()
    source = SimpleNamespace(id=parent_id, fixture_number=1, match_id=uuid4(), status="published")
    target = SimpleNamespace(id=target_id, fixture_number=2, match_id=uuid4(), home_team_id=team_id,
                             away_team_id=None, is_locked=False, version=2, status="published")
    official = SimpleNamespace(status=MatchStatus.COMPLETED, completed_at=datetime.now(timezone.utc), winner_team_id=None, team_a_id=team_id, team_b_id=uuid4())
    session.get = AsyncMock(return_value=official)
    run = FixtureGenerationRun(id=uuid4(), status="draft", configuration={})
    rows = [{"id": parent_id, "fixture_number": 1, "round_number": 1},
            {"id": target_id, "fixture_number": 2, "round_number": 2, "home_source": "winner:1"}]
    service.load = AsyncMock(return_value=(run, [source, target], rows))
    result = await service.progress(run.id)
    assert result["blocked"]
    assert str(target_id) in result["reviews"]
    assert target.home_team_id == team_id
    assert target.version == 2, "an existing downstream match must not be silently rewritten"


async def test_ready_guard_blocks_a_postponed_fixture():
    from app.core.exceptions import ConflictError
    service, session = mock_service()
    fixture = SimpleNamespace(id=uuid4(), generation_run_id=uuid4(), status="postponed")
    session.scalar = AsyncMock(return_value=fixture)
    from unittest.mock import patch
    with patch.object(FixturePlanningService, "load", AsyncMock(return_value=(SimpleNamespace(configuration={}), [], [{"id": fixture.id}]))):
        with pytest.raises(ConflictError, match="postponed"):
            await validate_fixture_activation(session, SimpleNamespace(id=uuid4()))
