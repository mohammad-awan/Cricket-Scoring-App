"""Stage 11 migrations, upgrade and downgrade, without a database.

Alembic's offline mode renders every operation to SQL, so these tests prove
both directions of the Stage 11 revisions compile (valid identifiers, no
calls that need a live connection) and preserve existing data: upgrades
only add nullable or defaulted columns and new tables.

A live round trip belongs on a disposable database:
    alembic downgrade 20261010_0010 && alembic upgrade head
"""

import io
import re
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BEFORE_STAGE11 = "20261010_0010"
STAGE11 = "20261013_0011"
COMPLETION = "20261014_0012"
SHORT_SIDES = "20261015_0013"


def alembic_config(buffer: io.StringIO) -> Config:
    config = Config(str(ROOT / "alembic.ini"), output_buffer=buffer)
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def render(direction: str, revision_range: str) -> str:
    buffer = io.StringIO()
    getattr(command, direction)(alembic_config(buffer), revision_range, sql=True)
    return buffer.getvalue()


def test_completion_revision_is_the_single_head() -> None:
    script = ScriptDirectory.from_config(alembic_config(io.StringIO()))

    assert script.get_heads() == [SHORT_SIDES]
    assert script.get_revision(SHORT_SIDES).down_revision == COMPLETION
    assert script.get_revision(COMPLETION).down_revision == STAGE11


@pytest.mark.parametrize(
    ("direction", "revision_range"),
    [
        ("upgrade", f"{BEFORE_STAGE11}:{STAGE11}"),
        ("upgrade", f"{STAGE11}:{COMPLETION}"),
        ("downgrade", f"{COMPLETION}:{STAGE11}"),
        ("downgrade", f"{STAGE11}:{BEFORE_STAGE11}"),
        ("upgrade", f"{COMPLETION}:{SHORT_SIDES}"),
        ("downgrade", f"{SHORT_SIDES}:{COMPLETION}"),
    ],
)
def test_stage11_migrations_render_in_both_directions(direction: str, revision_range: str) -> None:
    sql = render(direction, revision_range)
    target = revision_range.split(":")[1]

    assert f"version_num='{target}'" in sql


def test_identifiers_fit_postgresql_limit() -> None:
    sql = render("upgrade", f"{BEFORE_STAGE11}:{COMPLETION}")
    names = re.findall(r"CONSTRAINT (\w+)|INDEX (\w+)", sql)

    assert names
    assert all(len(name) <= 63 for pair in names for name in pair if name)


def test_completion_upgrade_preserves_existing_rows() -> None:
    sql = render("upgrade", f"{STAGE11}:{COMPLETION}")
    added_columns = re.findall(r"ALTER TABLE (\w+) ADD COLUMN (\w+) ([^;]+);", sql)

    assert {(table, column) for table, column, _ in added_columns} == {
        ("players", "sex"),
        ("tournaments", "series_id"),
        ("tournaments", "edition_number"),
        ("tournament_teams", "replaces_membership_id"),
        ("tournament_assets", "is_current"),
        ("tournament_assets", "original_filename"),
        ("tournament_assets", "created_by"),
    }
    for _, column, definition in added_columns:
        assert "NOT NULL" not in definition or "DEFAULT" in definition, column

    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "CREATE TABLE tournament_series" in sql
    assert "CREATE TABLE tournament_point_deductions" in sql


def test_completion_downgrade_removes_everything_it_added() -> None:
    sql = render("downgrade", f"{COMPLETION}:{STAGE11}")

    for statement in (
        "DROP TABLE tournament_point_deductions",
        "DROP TABLE tournament_series",
        "ALTER TABLE players DROP COLUMN sex",
        "ALTER TABLE tournaments DROP COLUMN series_id",
        "ALTER TABLE tournament_teams DROP COLUMN replaces_membership_id",
        "ALTER TABLE tournament_assets DROP COLUMN is_current",
        "DROP TYPE IF EXISTS player_sex",
    ):
        assert statement in sql


def test_short_sides_upgrade_keeps_existing_matches_on_full_sides() -> None:
    sql = render("upgrade", f"{COMPLETION}:{SHORT_SIDES}")

    assert "ALTER TABLE matches ADD COLUMN minimum_players_to_start INTEGER;" in sql
    assert "ALTER TABLE innings ADD COLUMN batting_side_size INTEGER;" in sql
    # Existing innings keep their all-out point from their real XI size.
    assert "UPDATE innings AS i" in sql
    assert "DROP" not in sql
