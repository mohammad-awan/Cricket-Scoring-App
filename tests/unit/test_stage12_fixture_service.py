from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.services.fixture import (
    FixtureService,
    FixtureGenerationResult,
    FixtureValidationError,
    FixtureNotFoundError,
    FixtureConflictError,
)
from app.models.entities.fixtures import (
    Fixture,
    FixtureGenerationRun,
    FixtureChangeAudit,
)


@pytest.fixture
def session():
    db = MagicMock()
    db.scalar = AsyncMock()
    db.scalars = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(session):
    return FixtureService(session)


def make_fixture(
    *,
    status="draft",
    version=1,
    locked=False,
    match_id=None,
):
    fixture = Fixture(
        id=uuid4(),
        tournament_id=uuid4(),
        generation_run_id=uuid4(),
        round_id=uuid4(),
        fixture_number=1,
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        status=status,
        version=version,
        is_locked=locked,
        match_id=match_id,
    )
    return fixture


def make_run(status="draft"):
    return FixtureGenerationRun(
        id=uuid4(),
        tournament_id=uuid4(),
        method="round_robin",
        configuration={},
        status=status,
    )


# --------------------------------------------------
# SERVICE BASICS
# --------------------------------------------------

def test_service_uses_supplied_session(service, session):
    assert service.session is session


def test_result_dataclass():
    result = FixtureGenerationResult(
        generation_run_id=uuid4(),
        tournament_id=uuid4(),
        fixture_count=6,
        round_count=3,
    )

    assert result.fixture_count == 6
    assert result.round_count == 3


# --------------------------------------------------
# GENERATION VALIDATION
# --------------------------------------------------

@pytest.mark.asyncio
async def test_generation_rejects_unknown_method(service, session):
    with pytest.raises(FixtureValidationError):
        await service.generate_fixtures(
            tournament_id=uuid4(),
            method="unknown",
        )

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_generation_rejects_insufficient_teams(service, session):
    service._approved_teams = AsyncMock(
        side_effect=FixtureValidationError(
            "At least two approved tournament teams are required."
        )
    )

    with pytest.raises(FixtureValidationError):
        await service.generate_fixtures(
            tournament_id=uuid4(),
            method="round_robin",
        )

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_random_generation_requires_seed(service, session):
    service._approved_teams = AsyncMock(return_value=[str(uuid4()), str(uuid4())])

    with pytest.raises(FixtureValidationError):
        await service.generate_fixtures(
            tournament_id=uuid4(),
            method="random",
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_round_robin_generation_saves_records(service, session):
    teams = [str(uuid4()) for _ in range(4)]
    service._approved_teams = AsyncMock(return_value=teams)
    tournament_id = uuid4()
    result = await service.generate_fixtures(
        tournament_id=tournament_id,
        method="round_robin",
    )
    assert result.tournament_id == tournament_id
    assert result.fixture_count == 6
    assert result.round_count == 3

    added = [
        call.args[0]
        for call in session.add.call_args_list
    ]
    assert sum(
        isinstance(item, FixtureGenerationRun)
        for item in added
    ) == 1
    assert sum(
        isinstance(item, Fixture)
        for item in added
    ) == 6
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_knockout_generation_creates_dependencies(service, session):
    from app.models.entities.fixtures import FixtureBracketDependency

    service._approved_teams = AsyncMock(return_value=[str(uuid4()) for _ in range(4)])
    result = await service.generate_fixtures(tournament_id=uuid4(), method="knockout")
    added = [
        call.args[0]
        for call in session.add.call_args_list
    ]
    dependencies = [
        item for item in added
        if isinstance(item, FixtureBracketDependency)
    ]
    assert result.fixture_count == 3
    assert len(dependencies) == 2
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_generation_rejects_missing_pairings(service, session):
    service._approved_teams = AsyncMock(return_value=[str(uuid4()), str(uuid4())])
    with pytest.raises(FixtureValidationError):
        await service.generate_fixtures(
            tournament_id=uuid4(),
            method="manual",
            configuration={},
        )

    session.add.assert_not_called()


# --------------------------------------------------
# PUBLICATION
# --------------------------------------------------

@pytest.mark.asyncio
async def test_publish_rejects_invalid_count(service, session):
    with pytest.raises(FixtureValidationError):
        await service.publish_generation(
            generation_run_id=uuid4(),
            expected_fixture_count=0,
        )

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_rejects_missing_run(service, session):
    session.scalar.return_value = None
    with pytest.raises(FixtureNotFoundError):
        await service.publish_generation(
            generation_run_id=uuid4(),
            expected_fixture_count=1,
        )


@pytest.mark.asyncio
async def test_publish_rejects_already_published_run(service, session):
    session.scalar.return_value = make_run(status="published")
    with pytest.raises(FixtureConflictError):
        await service.publish_generation(
            generation_run_id=uuid4(),
            expected_fixture_count=1,
        )


@pytest.mark.asyncio
async def test_publish_rejects_count_mismatch(service, session):
    session.scalar.return_value = make_run()
    result = MagicMock()
    result.all.return_value = [make_fixture()]
    session.scalars.return_value = result

    with pytest.raises(FixtureConflictError):
        await service.publish_generation(
            generation_run_id=uuid4(),
            expected_fixture_count=2,
        )


@pytest.mark.asyncio
async def test_legacy_publish_uses_validated_match_linking(service, session, monkeypatch):
    run = make_run()
    fixture = make_fixture()
    session.scalar.return_value = run
    result = MagicMock()
    result.all.return_value = [fixture]
    session.scalars.return_value = result
    from app.services.fixture_planning import FixturePlanningService
    publish = AsyncMock(return_value={"published_count": 1})
    monkeypatch.setattr(FixturePlanningService, "publish", publish)
    published_count = await service.publish_generation(generation_run_id=run.id, expected_fixture_count=1)
    assert published_count == 1
    publish.assert_awaited_once_with(run.id, {fixture.id: 1}, "Organizer confirmed fixture publication")
    session.commit.assert_not_awaited()


# --------------------------------------------------
# FIXTURE UPDATES
# --------------------------------------------------

@pytest.mark.asyncio
async def test_update_rejects_invalid_version(service, session):
    with pytest.raises(FixtureValidationError):
        await service.update_fixture(
            fixture_id=uuid4(),
            expected_version=0,
            changes={"notes": "Updated"},
        )


@pytest.mark.asyncio
async def test_update_rejects_unknown_field(service, session):
    with pytest.raises(FixtureValidationError):
        await service.update_fixture(
            fixture_id=uuid4(),
            expected_version=1,
            changes={"status": "completed"},
        )


@pytest.mark.asyncio
async def test_update_rejects_missing_fixture(service, session):
    session.scalar.return_value = None
    with pytest.raises(FixtureNotFoundError):
        await service.update_fixture(
            fixture_id=uuid4(),
            expected_version=1,
            changes={"notes": "Updated"},
        )


@pytest.mark.asyncio
async def test_update_rejects_locked_fixture(service, session):
    session.scalar.return_value = make_fixture(locked=True)
    with pytest.raises(FixtureConflictError):
        await service.update_fixture(
            fixture_id=uuid4(),
            expected_version=1,
            changes={"notes": "Updated"},
        )


@pytest.mark.asyncio
async def test_update_rejects_version_conflict(service, session):
    session.scalar.return_value = make_fixture(version=3)
    with pytest.raises(FixtureConflictError):
        await service.update_fixture(
            fixture_id=uuid4(),
            expected_version=2,
            changes={"notes": "Updated"},
        )


@pytest.mark.asyncio
async def test_update_rejects_same_teams(service, session):
    fixture = make_fixture()
    session.scalar.return_value = fixture
    with pytest.raises(FixtureValidationError):
        await service.update_fixture(
            fixture_id=fixture.id,
            expected_version=1,
            changes={
                "away_team_id": fixture.home_team_id,
            },
        )


@pytest.mark.asyncio
async def test_update_rejects_invalid_time_range(service, session):
    fixture = make_fixture()
    session.scalar.return_value = fixture
    start = datetime.now(timezone.utc)
    with pytest.raises(FixtureValidationError):
        await service.update_fixture(
            fixture_id=fixture.id,
            expected_version=1,
            changes={
                "scheduled_at": start,
                "ends_at": start - timedelta(hours=1),
            },
        )


@pytest.mark.asyncio
async def test_update_saves_audit_and_increments_version(service, session):
    fixture = make_fixture()
    session.scalar.return_value = fixture
    await service.update_fixture(
        fixture_id=fixture.id,
        expected_version=1,
        changes={"notes": "Rescheduled by organizer"},
    )
    assert fixture.notes == "Rescheduled by organizer"
    assert fixture.version == 2
    added = [
        call.args[0]
        for call in session.add.call_args_list
    ]
    audits = [
        item for item in added
        if isinstance(item, FixtureChangeAudit)
    ]
    assert len(audits) == 1
    assert audits[0].action == "updated"
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()
