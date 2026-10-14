"""Stage 11 completion: series/editions, branding assets, reserve
replacement, disciplinary deductions and player sex eligibility.

Revision ID: 20261014_0012
Revises: 20261013_0011

Existing rows are kept intact: every new column is nullable or has a
server default, players get sex = NULL, and existing tournaments belong
to no series. tournament_assets had no writer before this revision; any
duplicate rows for one tournament/kind are demoted to non-current before
the uniqueness index is created.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261014_0012"
down_revision = "20261013_0011"

branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)

PLAYER_SEX = postgresql.ENUM("male", "female", name="player_sex", create_type=False)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    # 1. Player sex (tournament eligibility).
    # Raw SQL keeps offline (--sql) generation working.
    op.execute("CREATE TYPE player_sex AS ENUM ('male', 'female')")
    op.add_column("players", sa.Column("sex", PLAYER_SEX, nullable=True))

    # 2. Series: groups the editions of one competition.
    op.create_table(
        "tournament_series",
        sa.Column("id", UUID, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("organizer", sa.String(160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_series"),
        sa.UniqueConstraint("slug", name="uq_tournament_series_slug"),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="tournament_series_name_not_blank",
        ),
    )

    op.add_column("tournaments", sa.Column("series_id", UUID, nullable=True))
    op.add_column("tournaments", sa.Column("edition_number", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tournaments_series_id_tournament_series",
        "tournaments",
        "tournament_series",
        ["series_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "tournaments_edition_number_positive",
        "tournaments",
        "edition_number IS NULL OR edition_number >= 1",
    )
    op.create_index("ix_tournaments_series_id", "tournaments", ["series_id"])

    # 3. Reserve teams replacing withdrawn entries.
    op.add_column(
        "tournament_teams",
        sa.Column("replaces_membership_id", UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_tournament_teams_replaces_membership_id_tournament_teams",
        "tournament_teams",
        "tournament_teams",
        ["replaces_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_tournament_team_replaces_membership",
        "tournament_teams",
        ["replaces_membership_id"],
    )

    # 4. Branding asset metadata.
    op.add_column(
        "tournament_assets",
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "tournament_assets",
        sa.Column("original_filename", sa.String(255), nullable=True),
    )
    op.add_column(
        "tournament_assets",
        sa.Column("created_by", sa.String(160), nullable=True),
    )
    op.execute(
        """
        UPDATE tournament_assets AS asset
        SET is_current = false
        FROM (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY tournament_id, kind
                       ORDER BY created_at DESC, id
                   ) AS position
            FROM tournament_assets
        ) AS ranked
        WHERE asset.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_check_constraint(
        "tournament_asset_kind_valid",
        "tournament_assets",
        "kind IN ('logo', 'cover')",
    )
    op.create_index(
        "uq_tournament_assets_current_kind",
        "tournament_assets",
        ["tournament_id", "kind"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    # 5. Disciplinary point deductions.
    op.create_table(
        "tournament_point_deductions",
        sa.Column("id", UUID, nullable=False),
        sa.Column(
            "tournament_id",
            UUID,
            sa.ForeignKey(
                "tournaments.id",
                ondelete="RESTRICT",
                name="fk_tournament_point_deductions_tournament_id_tournaments",
            ),
            nullable=False,
        ),
        sa.Column(
            "tournament_team_id",
            UUID,
            sa.ForeignKey(
                "tournament_teams.id",
                ondelete="RESTRICT",
                name="fk_tournament_point_deductions_team_id_tournament_teams",
            ),
            nullable=False,
        ),
        sa.Column(
            "match_id",
            UUID,
            sa.ForeignKey(
                "matches.id",
                ondelete="RESTRICT",
                name="fk_tournament_point_deductions_match_id_matches",
            ),
            nullable=True,
        ),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(160), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_point_deductions"),
        sa.CheckConstraint("points > 0", name="tournament_deduction_points_positive"),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="tournament_deduction_reason_not_blank",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_reason IS NULL) "
            "OR (revoked_at IS NOT NULL AND revoked_reason IS NOT NULL)",
            name="tournament_deduction_revocation_complete",
        ),
    )
    op.create_index(
        "ix_tournament_point_deductions_tournament_team",
        "tournament_point_deductions",
        ["tournament_id", "tournament_team_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tournament_point_deductions_tournament_team",
        table_name="tournament_point_deductions",
    )
    op.drop_table("tournament_point_deductions")

    op.drop_index("uq_tournament_assets_current_kind", table_name="tournament_assets")
    op.drop_constraint("tournament_asset_kind_valid", "tournament_assets", type_="check")
    for column in ("created_by", "original_filename", "is_current"):
        op.drop_column("tournament_assets", column)

    op.drop_constraint(
        "uq_tournament_team_replaces_membership",
        "tournament_teams",
        type_="unique",
    )
    op.drop_constraint(
        "fk_tournament_teams_replaces_membership_id_tournament_teams",
        "tournament_teams",
        type_="foreignkey",
    )
    op.drop_column("tournament_teams", "replaces_membership_id")

    op.drop_index("ix_tournaments_series_id", table_name="tournaments")
    op.drop_constraint("tournaments_edition_number_positive", "tournaments", type_="check")
    op.drop_constraint(
        "fk_tournaments_series_id_tournament_series",
        "tournaments",
        type_="foreignkey",
    )
    op.drop_column("tournaments", "edition_number")
    op.drop_column("tournaments", "series_id")
    op.drop_table("tournament_series")

    op.drop_column("players", "sex")
    op.execute("DROP TYPE IF EXISTS player_sex")
