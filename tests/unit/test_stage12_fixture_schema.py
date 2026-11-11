
from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy.orm import configure_mappers
import app.models  # noqa: F401
from app.db.base import Base


EXPECTED_TABLES = {
    "fixture_generation_runs",
    "fixture_rounds",
    "fixtures",
    "fixture_bracket_dependencies",
    "fixture_venue_availability",
    "fixture_scheduling_constraints",
    "fixture_change_audits",
}

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "845e2be3dfb1_stage12_fixture_persistence.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "stage12_fixture_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_seven_fixture_tables_registered():
    actual = set(Base.metadata.tables) & EXPECTED_TABLES
    assert actual == EXPECTED_TABLES


def test_sqlalchemy_relationships_configure():
    configure_mappers()


@pytest.mark.parametrize("table_name", sorted(EXPECTED_TABLES))
def test_fixture_tables_have_primary_keys(table_name):
    table = Base.metadata.tables[table_name]

    assert "id" in table.columns
    assert table.columns["id"].primary_key


@pytest.mark.parametrize(
    "table_name",
    [
        "fixture_generation_runs",
        "fixture_rounds",
        "fixtures",
        "fixture_venue_availability",
        "fixture_scheduling_constraints",
    ],
)
def test_tournament_foreign_key_exists(table_name):
    table = Base.metadata.tables[table_name]
    foreign_keys = {fk.target_fullname for fk in table.foreign_keys}
    assert "tournaments.id" in foreign_keys


def test_fixture_has_required_foreign_keys():
    table = Base.metadata.tables["fixtures"]
    targets = {fk.target_fullname for fk in table.foreign_keys}
    assert {
        "tournaments.id",
        "fixture_generation_runs.id",
        "fixture_rounds.id",
        "teams.id",
        "venues.id",
        "matches.id",
    }.issubset(targets)


def test_fixture_supports_unresolved_knockout_teams():
    table = Base.metadata.tables["fixtures"]
    assert table.columns["home_team_id"].nullable
    assert table.columns["away_team_id"].nullable
    assert table.columns["match_id"].nullable


def test_fixture_match_link_is_unique():
    table = Base.metadata.tables["fixtures"]
    unique_constraints = [
        constraint
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert any(
        {column.name for column in constraint.columns}
        == {"match_id"}
        for constraint in unique_constraints
    )


def test_bracket_dependencies_have_two_fixture_links():
    table = Base.metadata.tables["fixture_bracket_dependencies"]

    fixture_foreign_keys = [
        fk
        for fk in table.foreign_keys
        if fk.target_fullname == "fixtures.id"
    ]

    assert len(fixture_foreign_keys) == 2


def test_fixture_check_constraints_exist():
    table = Base.metadata.tables["fixtures"]

    checks = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert len(checks) >= 5


def test_fixture_foreign_keys_have_delete_policies():
    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]

        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                assert constraint.ondelete in {
                    "RESTRICT",
                    "SET NULL",
                }


def test_migration_revision_chain():
    migration = load_migration()
    assert migration.revision == "845e2be3dfb1"
    assert migration.down_revision == "20261015_0014"


def test_migration_has_no_unrelated_table_changes():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "op.alter_column(" not in source
    assert "op.drop_column(" not in source
    assert "op.create_table(" in source
    assert "op.drop_table(" in source


def test_migration_creates_only_expected_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    import ast
    tree = ast.parse(source)
    created = set()
    dropped = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Attribute):
            continue

        if not isinstance(node.func.value, ast.Name):
            continue

        if node.func.value.id != "op":
            continue

        if not node.args:
            continue

        if not isinstance(node.args[0], ast.Constant):
            continue

        if node.func.attr == "create_table":
            created.add(node.args[0].value)

        if node.func.attr == "drop_table":
            dropped.add(node.args[0].value)

    assert created == EXPECTED_TABLES
    assert dropped == EXPECTED_TABLES
