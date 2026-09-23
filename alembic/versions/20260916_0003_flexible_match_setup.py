"""Stage 3 flexible match setup configuration.

Revision ID: 20260916_0003
Revises: 20260908_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260916_0003"
down_revision: str | None = "20260908_0002"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    # Stage 2 required total_overs.
    # Stage 3 allows NULL = unlimited overs.
    #
    # NOTE: op.drop_constraint() re-applies the naming
    # convention to whatever name is passed in, so the
    # BASE name (without the "ck_" prefix) must be used
    # here -- the same base name used when the constraint
    # was originally declared. Passing the fully-rendered
    # name double-prefixes it and the DROP fails with
    # "constraint does not exist".
    op.drop_constraint(
        "matches_total_overs_positive",
        "matches",
        type_="check",
    )

    op.alter_column(
        "matches",
        "total_overs",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.create_check_constraint(
        "matches_total_overs_positive_when_set",
        "matches",
        "total_overs IS NULL OR total_overs > 0",
    )

    op.add_column(
        "matches",
        sa.Column(
            "players_per_side",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("11"),
        ),
    )

    op.add_column(
        "matches",
        sa.Column(
            "balls_per_over",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("6"),
        ),
    )

    op.add_column(
        "matches",
        sa.Column(
            "innings_per_team",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    op.create_check_constraint(
        "matches_players_per_side_minimum",
        "matches",
        "players_per_side >= 2",
    )

    op.create_check_constraint(
        "matches_balls_per_over_positive",
        "matches",
        "balls_per_over > 0",
    )

    op.create_check_constraint(
        "matches_innings_per_team_positive",
        "matches",
        "innings_per_team > 0",
    )


def downgrade() -> None:

    # Old Stage 2 schema cannot represent
    # unlimited-over matches.
    op.execute(
        sa.text(
            "UPDATE matches "
            "SET total_overs = 1 "
            "WHERE total_overs IS NULL"
        )
    )

    op.drop_constraint(
        "matches_innings_per_team_positive",
        "matches",
        type_="check",
    )

    op.drop_constraint(
        "matches_balls_per_over_positive",
        "matches",
        type_="check",
    )

    op.drop_constraint(
        "matches_players_per_side_minimum",
        "matches",
        type_="check",
    )

    op.drop_column(
        "matches",
        "innings_per_team",
    )

    op.drop_column(
        "matches",
        "balls_per_over",
    )

    op.drop_column(
        "matches",
        "players_per_side",
    )

    op.drop_constraint(
        "matches_total_overs_positive_when_set",
        "matches",
        type_="check",
    )

    op.alter_column(
        "matches",
        "total_overs",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_check_constraint(
        "matches_total_overs_positive",
        "matches",
        "total_overs > 0",
    )