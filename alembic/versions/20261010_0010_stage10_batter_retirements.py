"""Stage 10: batter retirement events.

Revision ID: 20261010_0010
Revises: 20261010_0009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261010_0010"
down_revision = "20261010_0009"

branch_labels = None
depends_on = None

RETIREMENT_TYPE_VALUES = ("retired_hurt", "retired_out")


def upgrade() -> None:
    bind = op.get_bind()
    retirement_type = postgresql.ENUM(
        *RETIREMENT_TYPE_VALUES,
        name="retirement_type",
        create_type=False,
    )
    retirement_type.create(bind, checkfirst=True)

    # Existing type from the Stage 5 migration.
    delivery_status = postgresql.ENUM(
        "recorded",
        "void",
        name="delivery_status",
        create_type=False,
    )

    def player_fk(name: str, *, nullable: bool = False) -> sa.Column:
        return sa.Column(
            name,
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "players.id",
                ondelete="RESTRICT",
                name=f"fk_batter_retirements_{name}_players",
            ),
            nullable=nullable,
        )

    op.create_table(
        "batter_retirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "matches.id",
                ondelete="CASCADE",
                name="fk_batter_retirements_match_id_matches",
            ),
            nullable=False,
        ),
        sa.Column(
            "innings_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "innings.id",
                ondelete="CASCADE",
                name="fk_batter_retirements_innings_id_innings",
            ),
            nullable=False,
        ),
        sa.Column("event_number", sa.Integer(), nullable=False),
        sa.Column("after_delivery_number", sa.Integer(), nullable=False),
        player_fk("player_id"),
        sa.Column("retirement_type", retirement_type, nullable=False),
        player_fk("replacement_player_id", nullable=True),
        sa.Column("selection_mode", sa.String(20), nullable=False),
        player_fk("striker_before_id"),
        player_fk("non_striker_before_id"),
        player_fk("striker_after_id"),
        player_fk("non_striker_after_id"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            delivery_status,
            nullable=False,
            server_default="recorded",
        ),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Nullable until Stage 10 authentication is implemented.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batter_retirements"),
        sa.UniqueConstraint(
            "innings_id",
            "event_number",
            name="uq_batter_retirements_innings_event_number",
        ),
        sa.CheckConstraint(
            "event_number > 0",
            name="batter_retirements_event_number_positive",
        ),
        sa.CheckConstraint(
            "after_delivery_number >= 0",
            name="batter_retirements_after_delivery_non_negative",
        ),
        sa.CheckConstraint(
            "selection_mode IN ('automatic', 'manual')",
            name="batter_retirements_selection_mode_valid",
        ),
        sa.CheckConstraint(
            "striker_before_id <> non_striker_before_id "
            "AND striker_after_id <> non_striker_after_id",
            name="batter_retirements_batters_must_differ",
        ),
        sa.CheckConstraint(
            "replacement_player_id IS NOT NULL "
            "OR retirement_type = 'retired_out'",
            name="batter_retirements_hurt_requires_replacement",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="batter_retirements_reason_not_blank",
        ),
        sa.CheckConstraint(
            "(status = 'recorded' AND void_reason IS NULL AND voided_at IS NULL) "
            "OR (status = 'void' AND void_reason IS NOT NULL AND voided_at IS NOT NULL)",
            name="batter_retirements_void_fields_together",
        ),
    )

    op.create_index("ix_batter_retirements_match_id", "batter_retirements", ["match_id"])
    op.create_index(
        "ix_batter_retirements_innings_status",
        "batter_retirements",
        ["innings_id", "status"],
    )
    op.create_index("ix_batter_retirements_player_id", "batter_retirements", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_batter_retirements_player_id", table_name="batter_retirements")
    op.drop_index("ix_batter_retirements_innings_status", table_name="batter_retirements")
    op.drop_index("ix_batter_retirements_match_id", table_name="batter_retirements")
    op.drop_table("batter_retirements")

    postgresql.ENUM(name="retirement_type").drop(op.get_bind(), checkfirst=True)
