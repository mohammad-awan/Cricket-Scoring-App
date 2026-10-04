"""Stage 5 extras, wickets and auditable corrections.

Revision ID: 20260927_0005
Revises: 20260924_0004
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260927_0005"
down_revision: str | None = "20260924_0004"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WICKET_VALUES = (
    "bowled",
    "caught",
    "lbw",
    "run_out",
    "stumped",
    "hit_wicket",
    "obstructing_field",
)


def upgrade() -> None:
    bind = op.get_bind()
    wicket_type = postgresql.ENUM(
        *WICKET_VALUES,
        name="wicket_type",
        create_type=False,
    )
    wicket_type.create(
        bind,
        checkfirst=True,
    )
    # =========================
    # EXTRA RUN COMPONENTS
    # =========================
    op.add_column(
        "deliveries",
        sa.Column(
            "wide_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "no_ball_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "bye_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "leg_bye_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # =========================
    # WICKET FIELDS
    # =========================
    op.add_column(
        "deliveries",
        sa.Column(
            "wicket_type",
            wicket_type,
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "dismissed_player_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "fielder_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "next_batter_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "wicket_end",
            sa.String(
                length=20
            ),
            nullable=True,
        ),
    )
    # Stage 4 officially wrote no extras.
    # This also protects old manual rows.
    op.execute(
        sa.text(
            "UPDATE deliveries "
            "SET wide_runs = extra_runs, "
            "is_legal_ball = false "
            "WHERE extra_runs > 0 "
            "AND wide_runs = 0 "
            "AND no_ball_runs = 0 "
            "AND bye_runs = 0 "
            "AND leg_bye_runs = 0"
        )
    )
    # =========================
    # FOREIGN KEYS
    # =========================
    op.create_foreign_key(
        op.f(
            "fk_deliveries_"
            "dismissed_player_id_players"
        ),
        "deliveries",
        "players",
        [
            "dismissed_player_id"
        ],
        [
            "id"
        ],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f(
            "fk_deliveries_"
            "fielder_id_players"
        ),
        "deliveries",
        "players",
        [
            "fielder_id"
        ],
        [
            "id"
        ],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f(
            "fk_deliveries_"
            "next_batter_id_players"
        ),
        "deliveries",
        "players",
        [
            "next_batter_id"
        ],
        [
            "id"
        ],
        ondelete="RESTRICT",
    )
    # =========================
    # DATABASE VALIDATION
    # =========================
    op.create_check_constraint(
        "deliveries_extra_components_non_negative",
        "deliveries",
        (
            "wide_runs >= 0 "
            "AND no_ball_runs >= 0 "
            "AND bye_runs >= 0 "
            "AND leg_bye_runs >= 0"
        ),
    )
    op.create_check_constraint(
        "deliveries_extra_runs_match_components",
        "deliveries",
        (
            "extra_runs = "
            "wide_runs + "
            "no_ball_runs + "
            "bye_runs + "
            "leg_bye_runs"
        ),
    )
    op.create_check_constraint(
        "deliveries_no_ball_single_penalty",
        "deliveries",
        "no_ball_runs IN (0, 1)",
    )
    op.create_check_constraint(
        "deliveries_wide_exclusive",
        "deliveries",
        (
            "NOT ("
            "wide_runs > 0 "
            "AND ("
            "no_ball_runs > 0 "
            "OR bye_runs > 0 "
            "OR leg_bye_runs > 0 "
            "OR batter_runs > 0"
            ")"
            ")"
        ),
    )
    op.create_check_constraint(
        "deliveries_bye_types_exclusive",
        "deliveries",
        (
            "NOT ("
            "bye_runs > 0 "
            "AND leg_bye_runs > 0"
            ")"
        ),
    )
    op.create_check_constraint(
        "deliveries_byes_not_batter_runs",
        "deliveries",
        (
            "NOT ("
            "(bye_runs > 0 "
            "OR leg_bye_runs > 0) "
            "AND batter_runs > 0"
            ")"
        ),
    )
    op.create_check_constraint(
        "deliveries_legal_ball_matches_extras",
        "deliveries",
        (
            "is_legal_ball = "
            "(wide_runs = 0 "
            "AND no_ball_runs = 0)"
        ),
    )
    op.create_check_constraint(
        "deliveries_wicket_fields_together",
        "deliveries",
        (
            "("
            "wicket_type IS NULL "
            "AND dismissed_player_id IS NULL"
            ") "
            "OR "
            "("
            "wicket_type IS NOT NULL "
            "AND dismissed_player_id IS NOT NULL"
            ")"
        ),
    )
    op.create_check_constraint(
        "deliveries_wicket_dependents_require_wicket",
        "deliveries",
        (
            "wicket_type IS NOT NULL "
            "OR ("
            "fielder_id IS NULL "
            "AND next_batter_id IS NULL"
            ")"
        ),
    )
    op.create_check_constraint(
        "deliveries_wicket_end_valid",
        "deliveries",
        (
            "wicket_end IS NULL "
            "OR wicket_end IN "
            "('striker_end', "
            "'non_striker_end')"
        ),
    )
    op.create_check_constraint(
        "deliveries_wicket_end_requires_run_out",
        "deliveries",
        (
            "wicket_end IS NULL "
            "OR wicket_type = 'run_out'"
        ),
    )
    # =========================
    # INDEXES
    # =========================
    op.create_index(
        op.f(
            "ix_deliveries_"
            "dismissed_player_id"
        ),
        "deliveries",
        [
            "dismissed_player_id"
        ],
    )
    op.create_index(
        op.f(
            "ix_deliveries_"
            "wicket_type"
        ),
        "deliveries",
        [
            "wicket_type"
        ],
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_deliveries_"
            "wicket_type"
        ),
        table_name="deliveries",
    )
    op.drop_index(
        op.f(
            "ix_deliveries_"
            "dismissed_player_id"
        ),
        table_name="deliveries",
    )

    for name in (
        "deliveries_wicket_end_requires_run_out",
        "deliveries_wicket_end_valid",
        "deliveries_wicket_dependents_require_wicket",
        "deliveries_wicket_fields_together",
        "deliveries_legal_ball_matches_extras",
        "deliveries_byes_not_batter_runs",
        "deliveries_bye_types_exclusive",
        "deliveries_wide_exclusive",
        "deliveries_no_ball_single_penalty",
        "deliveries_extra_runs_match_components",
        "deliveries_extra_components_non_negative",
    ):
        op.drop_constraint(
            name,
            "deliveries",
            type_="check",
        )
    op.drop_constraint(
        op.f(
            "fk_deliveries_"
            "next_batter_id_players"
        ),
        "deliveries",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f(
            "fk_deliveries_"
            "fielder_id_players"
        ),
        "deliveries",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f(
            "fk_deliveries_"
            "dismissed_player_id_players"
        ),
        "deliveries",
        type_="foreignkey",
    )
    op.drop_column(
        "deliveries",
        "wicket_end",
    )
    op.drop_column(
        "deliveries",
        "next_batter_id",
    )
    op.drop_column(
        "deliveries",
        "fielder_id",
    )
    op.drop_column(
        "deliveries",
        "dismissed_player_id",
    )
    op.drop_column(
        "deliveries",
        "wicket_type",
    )
    op.drop_column(
        "deliveries",
        "leg_bye_runs",
    )
    op.drop_column(
        "deliveries",
        "bye_runs",
    )
    op.drop_column(
        "deliveries",
        "no_ball_runs",
    )
    op.drop_column(
        "deliveries",
        "wide_runs",
    )
    postgresql.ENUM(
        *WICKET_VALUES,
        name="wicket_type",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )