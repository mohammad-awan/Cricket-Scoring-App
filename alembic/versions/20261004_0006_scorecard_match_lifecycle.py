"""Stage 6 scorecard and match lifecycle result fields.

Revision ID: 20261004_0006
Revises: 20260927_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20261004_0006"
down_revision: str | None = "20260927_0005"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column(
            "winner_team_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "result_type",
            sa.String(
                length=20
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "result_margin",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "completed_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        op.f(
            "fk_matches_"
            "winner_team_id_teams"
        ),
        "matches",
        "teams",
        ["winner_team_id"],
        ["id"],
        ondelete="SET NULL"
    )
    op.create_check_constraint(
        "matches_result_type_valid",
        "matches",
        (
            "result_type IS NULL "
            "OR result_type IN "
            "('runs', 'wickets', 'tie')"
        ),
    )
    op.create_check_constraint(
        "matches_result_margin_non_negative",
        "matches",
        (
            "result_margin IS NULL "
            "OR result_margin >= 0"
        ),
    )
    op.create_check_constraint(
        "matches_result_fields_valid",
        "matches",
        (
            "("
            "result_type IS NULL "
            "AND result_margin IS NULL"
            ") "
            "OR "
            "("
            "result_type = 'tie' "
            "AND result_margin = 0"
            ") "
            "OR "
            "("
            "result_type IN ('runs', 'wickets') "
            "AND result_margin > 0"
            ")"
        ),
    )
    op.create_index(
        op.f("ix_matches_winner_team_id"),
        "matches",
        ["winner_team_id"],
    )
    op.create_index(
        op.f("ix_matches_completed_at"),
        "matches",
        ["completed_at"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_matches_completed_at"
        ),
        table_name="matches",
    )
    op.drop_index(
        op.f(
            "ix_matches_winner_team_id"
        ),
        table_name="matches",
    )
    op.drop_constraint(
        "matches_result_fields_valid",
        "matches",
        type_="check",
    )
    op.drop_constraint(
        "matches_result_margin_non_negative",
        "matches",
        type_="check",
    )
    op.drop_constraint(
        "matches_result_type_valid",
        "matches",
        type_="check",
    )
    op.drop_constraint(
        op.f(
            "fk_matches_"
            "winner_team_id_teams"
        ),
        "matches",
        type_="foreignkey",
    )
    op.drop_column("matches", "completed_at")
    op.drop_column("matches", "result_margin")
    op.drop_column("matches", "result_type")
    op.drop_column("matches", "winner_team_id")