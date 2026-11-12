"""Run with python -m unittest tests.unit.test_player_jersey_number."""
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import CheckConstraint

from app.models.entities.players import Player
from app.schemas.players import PlayerCreate, PlayerUpdate


class JerseyNumberTests(unittest.TestCase):
    def test_create_update_and_clear(self):
        for number in (None, 0, 7, 56, 999):
            with self.subTest(number=number):
                self.assertEqual(PlayerCreate(full_name="Player", jersey_number=number).jersey_number, number)
                self.assertEqual(PlayerUpdate(jersey_number=number).model_dump(exclude_unset=True), {"jersey_number": number})
        self.assertIsNone(PlayerCreate(full_name="Existing player").jersey_number)
        self.assertNotIn("jersey_number", PlayerUpdate(full_name="Updated").model_dump(exclude_unset=True))

    def test_invalid_numbers(self):
        for value in (-1, 1000, 4.5, True, "seven", "7"):
            for schema, extra in ((PlayerCreate, {"full_name": "Player"}), (PlayerUpdate, {})):
                with self.subTest(value=value, schema=schema.__name__), self.assertRaises(ValidationError):
                    schema(jersey_number=value, **extra)

    def test_model_column_and_constraint(self):
        self.assertTrue(Player.__table__.c.jersey_number.nullable)
        constraints = [c for c in Player.__table__.constraints if isinstance(c, CheckConstraint)]
        self.assertTrue(any(c.name == "ck_players_player_jersey_number_range" for c in constraints))

    def test_upgrade_and_downgrade_sql(self):
        path = Path(__file__).parents[2] / "alembic/versions/20261112_0016_player_jersey_number.py"
        spec = importlib.util.spec_from_file_location("jersey_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.assertEqual(migration.down_revision, "20261112_0015")
        output = io.StringIO()
        context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output, "target_metadata": Player.metadata})
        with patch.object(migration, "op", Operations(context)):
            migration.upgrade()
            migration.downgrade()
        sql = output.getvalue()
        self.assertIn("ADD COLUMN jersey_number INTEGER", sql)
        self.assertIn("ADD CONSTRAINT ck_players_player_jersey_number_range CHECK", sql)
        self.assertIn("DROP CONSTRAINT ck_players_player_jersey_number_range", sql)
        self.assertIn("DROP COLUMN jersey_number", sql)


if __name__ == "__main__":
    unittest.main()
