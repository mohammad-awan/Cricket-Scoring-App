"""Stage 4 core ball-by-ball scoring support.

Revision ID: 20260924_0004
Revises: 20260916_0003
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260924_0004"
down_revision: str | None = ("20260916_0003")
branch_labels: (str | Sequence[str] | None) = None
depends_on: (str | Sequence[str] | None) = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column(
            "match_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
    )

    # Safe for development DBs that may
    # already contain test deliveries.
    op.execute(
        sa.text(
            "UPDATE deliveries AS d "
            "SET match_id = i.match_id "
            "FROM innings AS i "
            "WHERE d.innings_id = i.id "
            "AND d.match_id IS NULL"
        )
    )

    op.alter_column(
        "deliveries",
        "match_id",
        existing_type=postgresql.UUID(
            as_uuid=True
        ),
        nullable=False,
    )

    op.create_foreign_key(
        op.f(
            "fk_deliveries_match_id_matches"
        ),
        "deliveries",
        "matches",
        ["match_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        op.f(
            "ix_deliveries_match_id"
        ),
        "deliveries",
        ["match_id"],
    )

    op.create_index(
        op.f(
            "ix_deliveries_"
            "match_innings_sequence"
        ),
        "deliveries",
        [
            "match_id",
            "innings_id",
            "delivery_number",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_deliveries_"
            "match_innings_sequence"
        ),
        table_name="deliveries",
    )
    op.drop_index(
        op.f("ix_deliveries_match_id"), table_name="deliveries")
    op.drop_constraint(
        op.f("fk_deliveries_match_id_matches"), "deliveries", type_="foreignkey")
    op.drop_column("deliveries", "match_id")