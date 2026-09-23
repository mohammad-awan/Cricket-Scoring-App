"""Stage 1 baseline.

Revision ID: 20260903_0001
Revises:
Create Date: 2026-09-06
"""


from collections.abc import Sequence


revision: str = "20260903_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depend_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No feature tables are created in Stage 1."""


def downgrade() -> None:
    """The empty Stage 1 baseline has nothing to remove."""





