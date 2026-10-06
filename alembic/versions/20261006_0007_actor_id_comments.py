"""Stage 8 sync actor_id column comments with the ORM models.

Revision ID: 20261006_0007
Revises: 20261004_0006
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20261006_0007"
down_revision: str | None = "20261004_0006"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR_ID_COMMENT = "Nullable until Stage 10 authentication is implemented."

ACTOR_ID_TABLES = (
    "audit_logs",
    "deliveries",
    "delivery_corrections",
)


def upgrade() -> None:
    for table_name in ACTOR_ID_TABLES:
        op.alter_column(
            table_name,
            "actor_id",
            existing_type=postgresql.UUID(as_uuid=True),
            existing_nullable=True,
            comment=ACTOR_ID_COMMENT,
        )


def downgrade() -> None:
    for table_name in ACTOR_ID_TABLES:
        op.alter_column(
            table_name,
            "actor_id",
            existing_type=postgresql.UUID(as_uuid=True),
            existing_nullable=True,
            comment=None,
            existing_comment=ACTOR_ID_COMMENT,
        )
