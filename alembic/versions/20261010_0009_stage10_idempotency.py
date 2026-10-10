"""Stage 10: delivery idempotency protection.

Revision ID: 20261010_0009
Revises: 20261006_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261010_0009"
down_revision = "20261006_0008"

branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column(
            "client_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "deliveries",
        sa.Column(
            "client_event_fingerprint",
            sa.String(64),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_deliveries_match_client_event",
        "deliveries",
        ["match_id", "client_event_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_deliveries_match_client_event",
        "deliveries",
        type_="unique",
    )

    op.drop_column("deliveries", "client_event_fingerprint")
    op.drop_column("deliveries", "client_event_id")
