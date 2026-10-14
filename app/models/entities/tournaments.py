from __future__ import annotations
from datetime import date, datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    String,
    Text,
    UniqueConstraint,
    Boolean,
    ForeignKey,
    Integer,
    DateTime,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import TournamentStatus, db_enum
from uuid import UUID
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from app.models.entities.matches import Match


class TournamentSeries(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recurring competition; each Tournament row is one edition of it."""

    __tablename__ = "tournament_series"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    organizer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="tournament_series_name_not_blank",
        ),
    )


class Tournament(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "tournaments"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    season: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
        # Identity and branding
    code: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    sponsor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    geographic_scope: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="UTC",
        server_default="UTC",
    )
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    trophy_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Edition of a recurring competition (optional).
    series_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournament_series.id", ondelete="SET NULL"),
        nullable=True,
    )
    edition_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Registration
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_teams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_teams: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    maximum_teams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserve_team_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    registration_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        server_default="open",
    )
    entry_requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    roster_lock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replacement_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Publishing and venue
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    primary_venue_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("venues.id", ondelete="SET NULL"), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[TournamentStatus] = mapped_column(
        db_enum(TournamentStatus, "tournament_status"),
        nullable=False,
        default=TournamentStatus.DRAFT,
        server_default="draft",
    )
    matches: Mapped[list[Match]] = relationship(
        "Match",
        back_populates="tournament",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            "season",
            name="uq_tournaments_name_season",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="tournament_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(slug)) > 0",
            name="tournament_slug_not_blank",
        ),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="tournaments_dates_valid",
        ),
        CheckConstraint(
            "minimum_teams >= 2",
            name="tournaments_minimum_teams_valid",
        ),
        CheckConstraint(
            "maximum_teams IS NULL OR maximum_teams >= minimum_teams",
            name="tournaments_maximum_teams_valid",
        ),
        CheckConstraint(
            "reserve_team_limit >= 0",
            name="tournaments_reserve_limit_valid",
        ),
        CheckConstraint(
            "registration_mode IN ('open', 'invitational')",
            name="tournaments_registration_mode_valid",
        ),
        CheckConstraint(
            "registration_closes_at IS NULL OR registration_opens_at IS NULL "
            "OR registration_closes_at > registration_opens_at",
            name="tournaments_registration_window_valid",
        ),
        CheckConstraint(
            "edition_number IS NULL OR edition_number >= 1",
            name="tournaments_edition_number_positive",
        ),
        Index("ix_tournaments_status", "status"),
        Index("ix_tournaments_series_id", "series_id"),
        Index("ix_tournaments_name", "name"),
        Index("ix_tournaments_season", "season"),
    )



class TournamentRuleSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable, versioned rule snapshot. Services only ever append rows."""

    __tablename__ = "tournament_rule_sets"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    format_code: Mapped[str] = mapped_column(String(40), nullable=False)
    competition_structure: Mapped[str] = mapped_column(String(40), nullable=False)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(160))
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "version",
            name="uq_tournament_rules_version",
        ),
        CheckConstraint(
            "version >= 1",
            name="tournament_rules_version_positive",
        ),
        Index("ix_tournament_rule_sets_tournament_id", "tournament_id"),
    )


class TournamentTeam(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tournament_teams"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(160))
    seed: Mapped[int | None] = mapped_column(Integer)
    registration_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    captain_player_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
    )
    manager_name: Mapped[str | None] = mapped_column(String(160))
    group_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "tournament_groups.id",
            ondelete="SET NULL",
        ),
    )
    is_reserve: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # Set when a reserve entry is promoted to replace a withdrawn team.
    replaces_membership_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournament_teams.id", ondelete="SET NULL"),
    )

    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "team_id",
            name="uq_tournament_team_membership",
        ),
        UniqueConstraint(
            "replaces_membership_id",
            name="uq_tournament_team_replaces_membership",
        ),
        CheckConstraint(
            "seed IS NULL OR seed >= 1",
            name="tournament_team_seed_positive",
        ),
        CheckConstraint(
            "registration_status IN "
            "('pending', 'approved', 'rejected', 'withdrawn')",
            name="tournament_team_registration_status_valid",
        ),
        Index(
            "ix_tournament_teams_tournament_status",
            "tournament_id",
            "registration_status",
        ),
    )


class TournamentGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tournament_groups"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "name",
            name="uq_tournament_group_name",
        ),
    )


class TournamentRoster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tournament_rosters"

    tournament_team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "tournament_teams.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    player_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="batter",
        server_default="batter",
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "tournament_team_id",
            "player_id",
            name="uq_tournament_roster_player",
        ),
        CheckConstraint(
            "role IN ('batter', 'bowler', 'all_rounder', 'wicket_keeper')",
            name="tournament_roster_role_valid",
        ),
        Index("ix_tournament_rosters_player_id", "player_id"),
    )

class TournamentAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tournament_assets"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Previous uploads are kept for the audit trail; one current per kind.
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    original_filename: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(160))

    __table_args__ = (
        CheckConstraint(
            "byte_size > 0",
            name="tournament_asset_size_positive",
        ),
        CheckConstraint(
            "kind IN ('logo', 'cover')",
            name="tournament_asset_kind_valid",
        ),
        Index("ix_tournament_assets_tournament_id", "tournament_id"),
        Index(
            "uq_tournament_assets_current_kind",
            "tournament_id",
            "kind",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )



class TournamentVenue(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tournament_venues"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "tournaments.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    venue_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "venues.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "venue_id",
            name="uq_tournament_venue",
        ),
    )


class TournamentPointDeduction(UUIDPrimaryKeyMixin, Base):
    """Disciplinary points deduction. Rows are never deleted: a mistaken
    deduction is revoked with a reason so the history stays traceable."""

    __tablename__ = "tournament_point_deductions"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tournament_team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    match_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(160))
    revoked_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "points > 0",
            name="tournament_deduction_points_positive",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="tournament_deduction_reason_not_blank",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_reason IS NULL) "
            "OR (revoked_at IS NOT NULL AND revoked_reason IS NOT NULL)",
            name="tournament_deduction_revocation_complete",
        ),
        Index(
            "ix_tournament_point_deductions_tournament_team",
            "tournament_id",
            "tournament_team_id",
        ),
    )


class TournamentAuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tournament_audit_events"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_tournament_audit_events_tournament_created",
            "tournament_id",
            "created_at",
        ),
    )


__all__ = [
    "TournamentSeries",
    "Tournament",
    "TournamentRuleSet",
    "TournamentTeam",
    "TournamentGroup",
    "TournamentRoster",
    "TournamentVenue",
    "TournamentAsset",
    "TournamentPointDeduction",
    "TournamentAuditEvent",
]
