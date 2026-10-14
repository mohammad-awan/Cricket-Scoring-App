"""Short-handed sides: teams may start with fewer than a full side.

Revision ID: 20261015_0013
Revises: 20261014_0012

matches.minimum_players_to_start is NULL for every existing match, which
keeps today's rule (a full side is required). Existing innings get
batting_side_size from the batting team's actual selections, so their
all-out point is unchanged.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261015_0013"
down_revision = "20261014_0012"

branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("minimum_players_to_start", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "matches_minimum_players_valid",
        "matches",
        "minimum_players_to_start IS NULL OR "
        "(minimum_players_to_start >= 2 AND minimum_players_to_start <= players_per_side)",
    )

    op.add_column(
        "innings",
        sa.Column("batting_side_size", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE innings AS i
        SET batting_side_size = side.players
        FROM (
            SELECT match_id, team_id, count(*) AS players
            FROM match_players
            GROUP BY match_id, team_id
        ) AS side
        WHERE side.match_id = i.match_id
          AND side.team_id = i.batting_team_id
          AND side.players >= 2
        """
    )
    op.create_check_constraint(
        "innings_batting_side_size_minimum",
        "innings",
        "batting_side_size IS NULL OR batting_side_size >= 2",
    )


def downgrade() -> None:
    op.drop_constraint("innings_batting_side_size_minimum", "innings", type_="check")
    op.drop_column("innings", "batting_side_size")
    op.drop_constraint("matches_minimum_players_valid", "matches", type_="check")
    op.drop_column("matches", "minimum_players_to_start")
