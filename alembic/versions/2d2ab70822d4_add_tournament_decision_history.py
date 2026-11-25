"""add tournament decision history

Revision ID: 2d2ab70822d4
Revises: 20261121_0017
Create Date: 2026-11-25 13:19:11.660109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '2d2ab70822d4'
down_revision: Union[
    str,
    Sequence[str],
    None,
] = '20261121_0017'

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    op.create_table(
        "tournament_decisions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "tournament_id",
            sa.UUID(),
            sa.ForeignKey("tournaments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision_type", sa.String(60), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.String(160), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_tournament_decisions_tournament_id",
        "tournament_decisions",
        ["tournament_id"],
    )

    op.execute("""
        CREATE FUNCTION prevent_tournament_decision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'Tournament decision history is immutable';
        END;
        $$;
    """)

    op.execute("""
        CREATE TRIGGER tournament_decisions_immutable
        BEFORE UPDATE OR DELETE
        ON tournament_decisions
        FOR EACH ROW
        EXECUTE FUNCTION
            prevent_tournament_decision_mutation();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS
            tournament_decisions_immutable
        ON tournament_decisions;
    """)

    op.execute("""
        DROP FUNCTION IF EXISTS
            prevent_tournament_decision_mutation();
    """)

    op.drop_index(
        "ix_tournament_decisions_tournament_id",
        table_name="tournament_decisions",
    )
    op.drop_table("tournament_decisions")