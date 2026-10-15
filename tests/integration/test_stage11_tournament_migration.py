"""Read-only checks that the live database is at the Stage 11 schema.
Run after ``alembic upgrade head``.
Includes the Stage 11 match-rule snapshot protection migration.
"""

import pytest
from sqlalchemy import text
from app.db.session import AsyncSessionFactory
from tests.integration.stage11_support import live_db


pytestmark = [pytest.mark.integration, live_db]


STAGE11_REVISION = "20261015_0014"
STAGE11_TABLES = {
    "tournament_rule_sets",
    "tournament_groups",
    "tournament_teams",
    "tournament_rosters",
    "tournament_venues",
    "tournament_assets",
    "tournament_audit_events",
    "tournament_series",
    "tournament_point_deductions",
}


@pytest.mark.asyncio
async def test_database_is_at_stage11_revision() -> None:
    """Verify that the database is at the latest Stage 11 revision."""

    async with AsyncSessionFactory() as session:
        version = await session.scalar(
            text(
                "SELECT version_num "
                "FROM alembic_version"
            )
        )

    assert version == STAGE11_REVISION


@pytest.mark.asyncio
async def test_stage11_tables_columns_and_enum_exist() -> None:
    """Verify tournament tables, match columns, statuses and trigger."""

    async with AsyncSessionFactory() as session:
        tables = set(
            (
                await session.scalars(
                    text(
                        "SELECT table_name "
                        "FROM information_schema.tables "
                        "WHERE table_schema = current_schema()"
                    )
                )
            ).all()
        )
        match_columns = set(
            (
                await session.scalars(
                    text(
                        "SELECT column_name "
                        "FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'matches'"
                    )
                )
            ).all()
        )
        statuses = set(
            (
                await session.scalars(
                    text(
                        "SELECT unnest("
                        "enum_range(NULL::tournament_status)"
                        ")::text"
                    )
                )
            ).all()
        )
        rule_sets_trigger = await session.scalar(
            text(
                "SELECT 1 "
                "FROM pg_trigger "
                "WHERE tgname = "
                "'trg_tournament_rule_sets_immutable' "
                "AND NOT tgisinternal"
            )
        )

    assert STAGE11_TABLES <= tables
    assert "tournaments_rules_sets" not in tables
    assert {
        "tournament_ruleset_id",
        "effective_rules",
        "effective_rules_checksum",
        "rules_locked_at",
    } <= match_columns

    assert {
        "draft",
        "active",
        "completed",
        "archived",
        "registration_open",
        "registration_closed",
        "scheduled",
        "live",
        "suspended",
        "cancelled",
    } <= statuses

    assert rule_sets_trigger == 1


@pytest.mark.asyncio
async def test_legacy_matches_have_no_invented_rule_snapshots() -> None:
    """Verify legacy matches have no inconsistent snapshot metadata."""

    async with AsyncSessionFactory() as session:
        inconsistent = await session.scalar(
            text(
                "SELECT count(*) "
                "FROM matches "
                "WHERE rules_locked_at IS NULL "
                "AND tournament_ruleset_id IS NOT NULL"
            )
        )

    assert inconsistent == 0
