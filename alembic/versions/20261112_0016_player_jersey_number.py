"""Add optional player jersey numbers.

Revision ID: 20261112_0016
Revises: 20261112_0015
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0016"
down_revision = "20261112_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("jersey_number", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_players_player_jersey_number_range"),
        "players",
        "jersey_number IS NULL OR jersey_number BETWEEN 0 AND 999",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_players_player_jersey_number_range"), "players", type_="check")
    op.drop_column("players", "jersey_number")
