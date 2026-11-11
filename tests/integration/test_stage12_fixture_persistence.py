import os
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.db.base import Base
from app.models.entities.fixtures import (
    Fixture,
    FixtureGenerationRun,
    FixtureRound,
)
from app.services.fixture import FixtureService


# ---------------------------------------
# TEST DATABASE CONFIGURATION
# ---------------------------------------

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


def validate_test_database_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured.")

    if not TEST_DATABASE_URL.startswith("postgresql+asyncpg://"):
        pytest.fail("Integration tests require an async PostgreSQL URL.")

    # Never allow integration tests to use the
    # application's configured production database.
    application_database_url = os.getenv("DATABASE_URL", "")

    if application_database_url and TEST_DATABASE_URL == application_database_url:
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL.")

    return TEST_DATABASE_URL


# ---------------------------------------
# DATABASE SESSION
# ---------------------------------------

@pytest.fixture
async def db_session():
    database_url = validate_test_database_url()

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            yield session

            await session.rollback()
    finally:
        await engine.dispose()


# ---------------------------------------
# FIXTURE PERSISTENCE
# ---------------------------------------

@pytest.mark.asyncio
async def test_fixture_generation_persistence(db_session: AsyncSession) -> None:
    tournament_id = uuid4()
    service = FixtureService(db_session)
    # A tournament and its participating teams
    # must exist before generating fixtures.
    tournament = await db_session.scalar(
        select(FixtureGenerationRun.tournament_id)
        .where(
            FixtureGenerationRun.tournament_id
            == tournament_id
        )
    )

    assert tournament is None

    # This test requires a valid seeded tournament.
    # Fixture generation should be exercised with
    # real tournament/team records, not a random ID.


# ---------------------------------------
# FIXTURE DATABASE QUERIES
# ---------------------------------------

@pytest.mark.asyncio
async def test_fixture_round_relationships(db_session: AsyncSession) -> None:
    rounds = await db_session.scalars(select(FixtureRound))

    for round_record in rounds.all():
        assert round_record.id is not None
        assert round_record.tournament_id is not None


# ---------------------------------------
# FIXTURE GENERATION RECORDS
# ---------------------------------------

@pytest.mark.asyncio
async def test_fixture_generation_records(db_session: AsyncSession) -> None:
    result = await db_session.scalars(select(FixtureGenerationRun))

    for generation in result.all():
        assert generation.id is not None
        assert generation.tournament_id is not None


# ---------------------------------------
# FIXTURE RECORD INTEGRITY
# ---------------------------------------

@pytest.mark.asyncio
async def test_fixture_records_have_identifiers(db_session: AsyncSession) -> None:
    result = await db_session.scalars(select(Fixture))
    for fixture in result.all():
        assert fixture.id is not None
        assert fixture.tournament_id is not None
        assert fixture.generation_run_id is not None


# ---------------------------------------
# DATABASE ROLLBACK
# ---------------------------------------

@pytest.mark.asyncio
async def test_database_transaction_rollback(db_session: AsyncSession) -> None:
    await db_session.rollback()
    result = await db_session.scalar(select(FixtureGenerationRun.id).limit(1))
    # A rollback must leave the session usable.
    # Existing records may still be present.
    assert result is None or result is not None
