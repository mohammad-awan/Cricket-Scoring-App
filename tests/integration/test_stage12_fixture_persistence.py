"""Real fixture transactions on an explicitly configured disposable database.

The database must already be migrated. An outer transaction encloses fixture
setup and all service commits; every test rolls that transaction back.
"""
import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import Match, MatchStatus, Team, Tournament, TournamentTeam, TournamentVenue, Venue
from app.models.entities.fixtures import Fixture
from app.schemas.fixture_planning import FixturePlanRequest, FixturePlanSave, FixtureRegenerate
from app.services.fixture_planning import FixturePlanningService, validate_fixture_activation
from app.core.exceptions import ConflictError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def database():
    url = os.getenv("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a separate migrated PostgreSQL test database.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        pytest.fail("Fixture integration tests require PostgreSQL.")
    application = os.getenv("DATABASE_URL", "")
    if application and parsed.set(drivername="postgresql") == make_url(application).set(drivername="postgresql"):
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL.")
    if parsed.drivername in {"postgresql", "postgres"}:
        parsed = parsed.set(drivername="postgresql+psycopg")
    engine = create_async_engine(parsed, pool_pre_ping=True)
    async with engine.connect() as connection:
        outer = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            try:
                yield session
            finally:
                await session.rollback()
        await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def competition(database):
    tag = uuid4().hex[:8]
    tournament = Tournament(id=uuid4(), name=f"Fixture test {tag}", slug=f"fixture-test-{tag}",
                            timezone="UTC", status="registration_closed", start_date=date(2026, 11, 1), end_date=date(2026, 12, 31))
    teams = [Team(id=uuid4(), name=f"Fixture team {tag}-{index}", short_name=f"T{index}", code=f"FX{tag}{index}") for index in range(4)]
    venues = [Venue(id=uuid4(), name=f"Fixture ground {tag}-{index}", city="Test city") for index in range(2)]
    database.add_all([tournament, *teams, *venues])
    await database.flush()
    database.add_all([TournamentTeam(tournament_id=tournament.id, team_id=team.id,
                                    seed=index + 1, registration_status="approved", is_reserve=False) for index, team in enumerate(teams)])
    database.add_all([TournamentVenue(tournament_id=tournament.id, venue_id=venue.id) for venue in venues])
    await database.flush()
    request = FixturePlanSave(request_id=uuid4(), team_ids=[team.id for team in teams], venue_ids=[venue.id for venue in venues],
                              start_date=date(2026, 11, 12), end_date=date(2026, 11, 30), timezone="UTC", overs=20)
    return tournament, request


async def save_draft(database, competition, format_name="round_robin"):
    tournament, request = competition
    request = request.model_copy(update={"format": format_name})
    service = FixturePlanningService(database)
    result = await service.save(tournament.id, request)
    await database.commit()
    run_id = result["generation_run_id"]
    run, fixtures, rows = await service.load(run_id)
    return service, run_id, fixtures, request


async def test_save_and_publication_are_idempotent_and_create_real_matches(database, competition):
    service, run_id, fixtures, request = await save_draft(database, competition)
    replay = await service.save(competition[0].id, request)
    assert replay["generation_run_id"] == run_id and replay["replayed"]
    expected = {fixture.id: fixture.version for fixture in fixtures}
    result = await service.publish(run_id, expected, "Confirmed test draw")
    await database.commit()
    assert result["created_match_count"] == 6
    assert await database.scalar(select(func.count(Match.id)).where(Match.tournament_id == competition[0].id)) == 6
    again = await service.publish(run_id, expected, "Retry confirmation")
    assert again["replayed"] and again["created_match_count"] == 0
    for fixture in await service.repo.fixtures(run_id):
        assert fixture.match_id is not None
        match = await database.get(Match, fixture.match_id)
        assert (match.team_a_id, match.team_b_id, match.venue_id, match.scheduled_at) == (fixture.home_team_id, fixture.away_team_id, fixture.venue_id, fixture.scheduled_at)
        assert match.total_overs == 20


async def test_partial_publication_failure_rolls_back_all_matches(database, competition, monkeypatch):
    service, run_id, fixtures, _ = await save_draft(database, competition)
    expected = {fixture.id: fixture.version for fixture in fixtures}
    real_create = service.create_match
    calls = 0
    async def fail_second(fixture):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Injected Match failure")
        return await real_create(fixture)
    monkeypatch.setattr(service, "create_match", fail_second)
    with pytest.raises(RuntimeError, match="Injected Match failure"):
        await service.publish(run_id, expected, "Rollback test")
    await database.rollback()
    assert await database.scalar(select(func.count(Match.id)).where(Match.tournament_id == competition[0].id)) == 0
    remaining = await service.repo.fixtures(run_id)
    assert all(fixture.status == "draft" and fixture.match_id is None and fixture.version == 1 for fixture in remaining)


async def test_official_winners_advance_but_corrections_flag_the_linked_final(database, competition):
    service, run_id, fixtures, _ = await save_draft(database, competition, "knockout")
    await service.publish(run_id, {fixture.id: fixture.version for fixture in fixtures}, "Confirm bracket")
    await database.commit()
    first_round = [fixture for fixture in await service.repo.fixtures(run_id) if fixture.match_id]
    assert len(first_round) == 2
    for fixture in first_round:
        match = await database.get(Match, fixture.match_id)
        match.status, match.winner_team_id = MatchStatus.COMPLETED, match.team_a_id
        match.result_type, match.result_margin = "runs", 10
        match.completed_at = datetime.now(timezone.utc)
    await database.flush()
    await service.progress(run_id)
    await database.commit()
    final = next(fixture for fixture in await service.repo.fixtures(run_id) if fixture.fixture_number == 3)
    assert final.match_id is not None
    original_home = final.home_team_id
    source_match = await database.get(Match, first_round[0].match_id)
    source_match.winner_team_id = source_match.team_b_id
    await database.flush()
    result = await service.progress(run_id)
    assert str(final.id) in result["reviews"]
    assert final.home_team_id == original_home
    final_match = await database.get(Match, final.match_id)
    with pytest.raises(ConflictError, match="review"):
        await validate_fixture_activation(database, final_match)


async def test_regeneration_preserves_pinned_fixture_identity_and_allocation(database, competition):
    service, run_id, fixtures, request = await save_draft(database, competition)
    fixed = fixtures[0]
    fixed.is_locked = True
    await database.flush()
    before = (fixed.id, fixed.home_team_id, fixed.away_team_id, fixed.venue_id, fixed.scheduled_at, fixed.ends_at, fixed.version)
    replacement = FixturePlanRequest.model_validate(request.model_dump(exclude={"request_id"}))
    replacement.times = [replacement.times[-1]]
    payload = FixtureRegenerate(expected_versions={fixture.id: fixture.version for fixture in fixtures}, configuration=replacement)
    result = await service.regenerate(run_id, payload)
    assert result["pinned_count"] == 1
    await database.refresh(fixed)
    assert (fixed.id, fixed.home_team_id, fixed.away_team_id, fixed.venue_id, fixed.scheduled_at, fixed.ends_at, fixed.version) == before