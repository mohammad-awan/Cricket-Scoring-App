
"""Stage 13 tournament awards and closeout.

Revision ID: 20261121_0017
Revises: 20261112_0016
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261121_0017"
down_revision = "20261112_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_awards",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "tournament_id",
            sa.UUID(),
            sa.ForeignKey(
                "tournaments.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("award_code", sa.String(60), nullable=False),
        sa.Column(
            "player_id",
            sa.UUID(),
            sa.ForeignKey(
                "players.id", ondelete="RESTRICT"
            ),
        ),
        sa.Column(
            "team_id",
            sa.UUID(),
            sa.ForeignKey(
                "teams.id", ondelete="RESTRICT"
            ),
        ),
        sa.Column(
            "status", sa.String(20), nullable=False
        ),
        sa.Column(
            "selection_method",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "confirmed_by", sa.String(160)
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tournament_id",
            "award_code",
            name="uq_tournament_award_code",
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'revoked')",
            name="ck_tournament_award_status",
        ),
        sa.CheckConstraint(
            "selection_method IN ('manual', 'statistical')",
            name="ck_tournament_award_method",
        ),
        sa.CheckConstraint(
            "(player_id IS NOT NULL) <> "
            "(team_id IS NOT NULL)",
            name="ck_tournament_award_recipient",
        ),
    )

    op.create_index(
        "ix_tournament_awards_tournament_id",
        "tournament_awards",
        ["tournament_id"],
    )

    op.create_table(
        "tournament_closeouts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "tournament_id",
            sa.UUID(),
            sa.ForeignKey(
                "tournaments.id", ondelete="RESTRICT"
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "champion_team_id",
            sa.UUID(),
            sa.ForeignKey(
                "teams.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "snapshot",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "is_frozen",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "finalized_by",
            sa.String(160),
        ),
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "reopened_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "reopen_reason",
            sa.Text(),
        ),
    )


def downgrade() -> None:
    op.drop_table("tournament_closeouts")
    op.drop_index(
        "ix_tournament_awards_tournament_id",
        table_name="tournament_awards",
    )
    op.drop_table("tournament_awards")
