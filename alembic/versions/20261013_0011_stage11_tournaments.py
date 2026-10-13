"""Stage 11: tournament competition management.

Revision ID: 20261013_0011
Revises: 20261010_0010

Existing tournament and match rows are kept intact: new tournament
columns are nullable or have server defaults, and legacy matches keep
NULL rule snapshots (no historical rule versions are invented).

Downgrade note: PostgreSQL cannot drop enum values, so the extended
``tournament_status`` values remain after a downgrade. Move any
tournaments using them back to draft/active/completed/archived first.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261013_0011"
down_revision = "20261010_0010"

branch_labels = None
depends_on = None


NEW_TOURNAMENT_STATUSES = (
    "registration_open",
    "registration_closed",
    "scheduled",
    "live",
    "suspended",
    "cancelled",
)

UUID = postgresql.UUID(as_uuid=True)


def _id() -> sa.Column:
    return sa.Column("id", UUID, nullable=False)


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


def _fk(
    table: str,
    column: str,
    referred: str,
    *,
    ondelete: str = "RESTRICT",
    nullable: bool = False,
) -> sa.Column:
    return sa.Column(
        column,
        UUID,
        sa.ForeignKey(
            f"{referred}.id",
            ondelete=ondelete,
            name=f"fk_{table}_{column}_{referred}",
        ),
        nullable=nullable,
    )


def _drop_misnamed_draft_table() -> None:
    """An earlier draft model used ``tournaments_rules_sets``. It was
    never part of a migration, but guard against a manually created copy."""

    if op.get_context().as_sql:
        return

    bind = op.get_bind()
    if not sa.inspect(bind).has_table("tournaments_rules_sets"):
        return

    rows = bind.execute(sa.text("SELECT count(*) FROM tournaments_rules_sets")).scalar()
    if rows:
        raise RuntimeError(
            "Table tournaments_rules_sets contains data. Migrate its rows "
            "into tournament_rule_sets manually before upgrading."
        )

    op.drop_table("tournaments_rules_sets")


def upgrade() -> None:
    # 1. Extend the tournament_status enum. ADD VALUE must commit before
    #    the new values can be used, so run it outside the transaction.
    with op.get_context().autocommit_block():
        for value in NEW_TOURNAMENT_STATUSES:
            op.execute(
                f"ALTER TYPE tournament_status ADD VALUE IF NOT EXISTS '{value}'"
            )

    _drop_misnamed_draft_table()

    # 2. Stage 11 columns on tournaments.
    tournament_columns = [
        sa.Column("code", sa.String(40), nullable=True),
        sa.Column("sponsor", sa.String(160), nullable=True),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("geographic_scope", sa.String(80), nullable=True),
        sa.Column("location", sa.String(160), nullable=True),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("contact_email", sa.String(254), nullable=True),
        sa.Column("contact_phone", sa.String(40), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("trophy_name", sa.String(160), nullable=True),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_teams", sa.Integer(), nullable=True),
        sa.Column("minimum_teams", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("maximum_teams", sa.Integer(), nullable=True),
        sa.Column("reserve_team_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "registration_mode",
            sa.String(20),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "entry_requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("roster_lock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("primary_venue_id", UUID, nullable=True),
    ]
    for column in tournament_columns:
        op.add_column("tournaments", column)

    op.create_unique_constraint("uq_tournaments_code", "tournaments", ["code"])
    op.create_foreign_key(
        "fk_tournaments_primary_venue_id_venues",
        "tournaments",
        "venues",
        ["primary_venue_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for name, condition in (
        ("tournaments_minimum_teams_valid", "minimum_teams >= 2"),
        (
            "tournaments_maximum_teams_valid",
            "maximum_teams IS NULL OR maximum_teams >= minimum_teams",
        ),
        ("tournaments_reserve_limit_valid", "reserve_team_limit >= 0"),
        (
            "tournaments_registration_mode_valid",
            "registration_mode IN ('open', 'invitational')",
        ),
        (
            "tournaments_registration_window_valid",
            "registration_closes_at IS NULL OR registration_opens_at IS NULL "
            "OR registration_closes_at > registration_opens_at",
        ),
    ):
        op.create_check_constraint(name, "tournaments", condition)

    # 3. Tournament tables, in foreign-key order.
    op.create_table(
        "tournament_rule_sets",
        _id(),
        _fk("tournament_rule_sets", "tournament_id", "tournaments"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("format_code", sa.String(40), nullable=False),
        sa.Column("competition_structure", sa.String(40), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_rule_sets"),
        sa.UniqueConstraint(
            "tournament_id",
            "version",
            name="uq_tournament_rules_version",
        ),
        sa.CheckConstraint("version >= 1", name="tournament_rules_version_positive"),
    )
    op.create_index(
        "ix_tournament_rule_sets_tournament_id",
        "tournament_rule_sets",
        ["tournament_id"],
    )

    # Rule versions are append-only: block in-place edits at the database.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_tournament_rule_set_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'tournament_rule_sets rows are immutable; create a new version instead';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tournament_rule_sets_immutable
        BEFORE UPDATE ON tournament_rule_sets
        FOR EACH ROW EXECUTE FUNCTION prevent_tournament_rule_set_update()
        """
    )

    op.create_table(
        "tournament_groups",
        _id(),
        _fk("tournament_groups", "tournament_id", "tournaments"),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_groups"),
        sa.UniqueConstraint("tournament_id", "name", name="uq_tournament_group_name"),
    )

    op.create_table(
        "tournament_teams",
        _id(),
        _fk("tournament_teams", "tournament_id", "tournaments"),
        _fk("tournament_teams", "team_id", "teams"),
        sa.Column("display_name", sa.String(160), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column(
            "registration_status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        _fk(
            "tournament_teams",
            "captain_player_id",
            "players",
            ondelete="SET NULL",
            nullable=True,
        ),
        sa.Column("manager_name", sa.String(160), nullable=True),
        _fk(
            "tournament_teams",
            "group_id",
            "tournament_groups",
            ondelete="SET NULL",
            nullable=True,
        ),
        sa.Column(
            "is_reserve",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_teams"),
        sa.UniqueConstraint(
            "tournament_id",
            "team_id",
            name="uq_tournament_team_membership",
        ),
        sa.CheckConstraint("seed IS NULL OR seed >= 1", name="tournament_team_seed_positive"),
        sa.CheckConstraint(
            "registration_status IN ('pending', 'approved', 'rejected', 'withdrawn')",
            name="tournament_team_registration_status_valid",
        ),
    )
    op.create_index(
        "ix_tournament_teams_tournament_status",
        "tournament_teams",
        ["tournament_id", "registration_status"],
    )

    op.create_table(
        "tournament_rosters",
        _id(),
        _fk("tournament_rosters", "tournament_team_id", "tournament_teams"),
        _fk("tournament_rosters", "player_id", "players"),
        sa.Column("role", sa.String(40), nullable=False, server_default="batter"),
        sa.Column(
            "is_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_rosters"),
        sa.UniqueConstraint(
            "tournament_team_id",
            "player_id",
            name="uq_tournament_roster_player",
        ),
        sa.CheckConstraint(
            "role IN ('batter', 'bowler', 'all_rounder', 'wicket_keeper')",
            name="tournament_roster_role_valid",
        ),
    )
    op.create_index("ix_tournament_rosters_player_id", "tournament_rosters", ["player_id"])

    op.create_table(
        "tournament_venues",
        _id(),
        _fk("tournament_venues", "tournament_id", "tournaments"),
        _fk("tournament_venues", "venue_id", "venues"),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_venues"),
        sa.UniqueConstraint("tournament_id", "venue_id", name="uq_tournament_venue"),
    )

    op.create_table(
        "tournament_assets",
        _id(),
        _fk("tournament_assets", "tournament_id", "tournaments"),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_assets"),
        sa.UniqueConstraint("object_key", name="uq_tournament_assets_object_key"),
        sa.CheckConstraint("byte_size > 0", name="tournament_asset_size_positive"),
    )
    op.create_index(
        "ix_tournament_assets_tournament_id",
        "tournament_assets",
        ["tournament_id"],
    )

    op.create_table(
        "tournament_audit_events",
        _id(),
        _fk("tournament_audit_events", "tournament_id", "tournaments"),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(160), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tournament_audit_events"),
    )
    op.create_index(
        "ix_tournament_audit_events_tournament_created",
        "tournament_audit_events",
        ["tournament_id", "created_at"],
    )

    # 4. Rule snapshot columns on matches (NULL for legacy matches).
    op.add_column("matches", sa.Column("tournament_ruleset_id", UUID, nullable=True))
    op.add_column("matches", sa.Column("effective_rules", postgresql.JSONB(), nullable=True))
    op.add_column("matches", sa.Column("effective_rules_checksum", sa.String(64), nullable=True))
    op.add_column(
        "matches",
        sa.Column("rules_locked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 5. Match constraints.
    op.create_foreign_key(
        "fk_matches_tournament_ruleset_id_tournament_rule_sets",
        "matches",
        "tournament_rule_sets",
        ["tournament_ruleset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "matches_rule_snapshot_complete",
        "matches",
        "(tournament_ruleset_id IS NULL AND effective_rules IS NULL "
        "AND effective_rules_checksum IS NULL AND rules_locked_at IS NULL) "
        "OR (tournament_ruleset_id IS NOT NULL AND effective_rules IS NOT NULL "
        "AND effective_rules_checksum IS NOT NULL AND rules_locked_at IS NOT NULL)",
    )
    op.create_index(
        "ix_matches_tournament_ruleset_id",
        "matches",
        ["tournament_ruleset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_matches_tournament_ruleset_id", table_name="matches")
    op.drop_constraint("matches_rule_snapshot_complete", "matches", type_="check")
    op.drop_constraint(
        "fk_matches_tournament_ruleset_id_tournament_rule_sets",
        "matches",
        type_="foreignkey",
    )
    for column in (
        "rules_locked_at",
        "effective_rules_checksum",
        "effective_rules",
        "tournament_ruleset_id",
    ):
        op.drop_column("matches", column)

    op.drop_index(
        "ix_tournament_audit_events_tournament_created",
        table_name="tournament_audit_events",
    )
    op.drop_table("tournament_audit_events")
    op.drop_index("ix_tournament_assets_tournament_id", table_name="tournament_assets")
    op.drop_table("tournament_assets")
    op.drop_table("tournament_venues")
    op.drop_index("ix_tournament_rosters_player_id", table_name="tournament_rosters")
    op.drop_table("tournament_rosters")
    op.drop_index("ix_tournament_teams_tournament_status", table_name="tournament_teams")
    op.drop_table("tournament_teams")
    op.drop_table("tournament_groups")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_tournament_rule_sets_immutable "
        "ON tournament_rule_sets"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_tournament_rule_set_update()")
    op.drop_index(
        "ix_tournament_rule_sets_tournament_id",
        table_name="tournament_rule_sets",
    )
    op.drop_table("tournament_rule_sets")

    for name in (
        "tournaments_registration_window_valid",
        "tournaments_registration_mode_valid",
        "tournaments_reserve_limit_valid",
        "tournaments_maximum_teams_valid",
        "tournaments_minimum_teams_valid",
    ):
        op.drop_constraint(name, "tournaments", type_="check")

    op.drop_constraint(
        "fk_tournaments_primary_venue_id_venues",
        "tournaments",
        type_="foreignkey",
    )
    op.drop_constraint("uq_tournaments_code", "tournaments", type_="unique")

    for column in (
        "primary_venue_id",
        "is_published",
        "replacement_cutoff_at",
        "roster_lock_at",
        "entry_requires_approval",
        "registration_mode",
        "reserve_team_limit",
        "maximum_teams",
        "minimum_teams",
        "expected_teams",
        "registration_closes_at",
        "registration_opens_at",
        "trophy_name",
        "terms",
        "contact_phone",
        "contact_email",
        "website",
        "location",
        "geographic_scope",
        "category",
        "timezone",
        "code",
    ):
        op.drop_column("tournaments", column)
