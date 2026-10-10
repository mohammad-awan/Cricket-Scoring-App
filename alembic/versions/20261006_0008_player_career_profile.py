"""Stage 9 player detail and career profile.

Revision ID: 20261006_0008
Revises: 20261006_0007
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20261006_0008"
down_revision: str | None = "20261006_0007"


branch_lable: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BATTING_HAND_VALUES = ("right", "left")
BOWLING_ARM_VALUES = ("right", "left", "none")
BOWLING_STYLE_VALUES = (
    "fast",
    "fast_medium",
    "medium_fast",
    "medium",
    "off_break",
    "leg_break",
    "orthodox",
    "wrist_spin",
    "mystery_spin",
    "other",
)


def enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(
        *values,
        name=name,
        create_type=False

    )


def upgrade() -> None:
    bind = op.get_bind()
    batting_hand = enum("batting_hand", BATTING_HAND_VALUES)
    bowling_arm = enum("bowling_arm", BOWLING_ARM_VALUES)
    bowling_style = enum("bowling_style", BOWLING_STYLE_VALUES)
    batting_hand.create(bind, checkfirst=True)
    bowling_arm.create(bind, checkfirst=True)
    bowling_style.create(bind, checkfirst=True)
    op.add_column(
        "players",
        sa.Column(
            "batting_hand",
            batting_hand,
            nullable=True,
        ),
    )
    op.add_column(
        "players",
        sa.Column(
            "bowling_arm",
            bowling_arm,
            nullable=True,
        ),
    )
    op.add_column(
        "players",
        sa.Column(
            "bowling_style",
            bowling_style,
            nullable=True,
        ),
    )
    op.create_check_constraint(
        (
            "players_no_bowling_"
            "has_no_style"
        ),
        "players",
        (
            "bowling_arm <> 'none' "
            "OR bowling_style IS NULL"
        ),
    )
    op.create_check_constraint(
        (
            "players_bowling_style_"
            "requires_arm"
        ),
        "players",
        (
            "bowling_style IS NULL "
            "OR bowling_arm IS NOT NULL"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint(
        (
            "players_bowling_style_"
            "requires_arm"
        ),
        "players",
        type="check",
    )

    op.drop_constraint(
        (
            "players_no_bowling_"
            "has_no_style"
        ),
        "players",
        type="check",
    )

    op.drop_column("players", "bowling_style")
    op.drop_column("players", "bowling_arm")
    op.drop_column("players", "batting_hand")
    enum("bowling_style", BOWLING_STYLE_VALUES).drop(bind, checkfirst=True)
    enum("bowling_arm", BOWLING_ARM_VALUES).drop(bind, checkfirst=True)
    enum("batting_hand", BATTING_HAND_VALUES).drop(bind, checkfirst=True)

