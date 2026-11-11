
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FixtureGenerationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fixture_generation_runs"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer)
    algorithm_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="1.0",
        server_default="1.0",
    )
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft",
        server_default="draft",
    )
    created_by: Mapped[str | None] = mapped_column(String(160))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rounds: Mapped[list["FixtureRound"]] = relationship(
        "FixtureRound",
        back_populates="generation_run",
        lazy="raise_on_sql",
    )
    fixtures: Mapped[list["Fixture"]] = relationship(
        "Fixture",
        back_populates="generation_run",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        CheckConstraint(
            "method IN ('manual', 'random', "
            "'round_robin', 'knockout')",
            name="fixture_generation_method_valid",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', "
            "'cancelled')",
            name="fixture_generation_status_valid",
        ),
        Index(
            "ix_fixture_generation_runs_tournament",
            "tournament_id",
        ),
    )


class FixtureRound(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fixture_rounds"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "fixture_generation_runs.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(
        String(40), nullable=False, default="league",
        server_default="league",
    )
    name: Mapped[str | None] = mapped_column(String(100))
    generation_run: Mapped["FixtureGenerationRun"] = (
        relationship(
            "FixtureGenerationRun",
            back_populates="rounds",
            lazy="raise_on_sql",
        )
    )
    fixtures: Mapped[list["Fixture"]] = relationship(
        "Fixture",
        back_populates="round",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "generation_run_id",
            "round_number",
            "stage",
            name="uq_fixture_round_generation_number_stage",
        ),
        CheckConstraint(
            "round_number >= 1",
            name="fixture_round_number_positive",
        ),
        Index(
            "ix_fixture_rounds_tournament",
            "tournament_id",
        ),
    )


class Fixture(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fixtures"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "fixture_generation_runs.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    round_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fixture_rounds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fixture_number: Mapped[int] = mapped_column(Integer, nullable=False)
    home_team_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    away_team_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    venue_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("venues.id", ondelete="SET NULL"),
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft",
        server_default="draft",
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        server_default=text("false"),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        server_default="1",
    )
    match_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        unique=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_run: Mapped["FixtureGenerationRun"] = (
        relationship(
            "FixtureGenerationRun",
            back_populates="fixtures",
            lazy="raise_on_sql",
        )
    )
    round: Mapped["FixtureRound"] = relationship(
        "FixtureRound",
        back_populates="fixtures",
        lazy="raise_on_sql",
    )
    match = relationship(
        "Match",
        foreign_keys=[match_id],
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "generation_run_id",
            "fixture_number",
            name="uq_fixture_generation_number",
        ),
        CheckConstraint(
            "fixture_number >= 1",
            name="fixture_number_positive",
        ),
        CheckConstraint(
            "version >= 1",
            name="fixture_version_positive",
        ),
        CheckConstraint(
            "home_team_id IS NULL "
            "OR away_team_id IS NULL "
            "OR home_team_id <> away_team_id",
            name="fixture_teams_must_differ",
        ),
        CheckConstraint(
            "ends_at IS NULL OR scheduled_at IS NULL "
            "OR ends_at > scheduled_at",
            name="fixture_schedule_window_valid",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', "
            "'postponed', 'cancelled', 'completed')",
            name="fixture_status_valid",
        ),
        Index(
            "ix_fixtures_tournament_status",
            "tournament_id",
            "status",
        ),
        Index(
            "ix_fixtures_scheduled_at",
            "scheduled_at",
        ),
        Index(
            "ix_fixtures_round_id",
            "round_id",
        ),
    )


class FixtureBracketDependency(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fixture_bracket_dependencies"

    fixture_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fixtures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_fixture_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fixtures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_side: Mapped[str] = mapped_column(String(10), nullable=False)
    advancement: Mapped[str] = mapped_column(
        String(10), nullable=False, default="winner",
        server_default="winner",
    )

    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "target_side",
            name="uq_fixture_bracket_target_side",
        ),
        CheckConstraint(
            "fixture_id <> source_fixture_id",
            name="fixture_bracket_not_self_referencing",
        ),
        CheckConstraint(
            "target_side IN ('home', 'away')",
            name="fixture_bracket_side_valid",
        ),
        CheckConstraint(
            "advancement IN ('winner', 'loser')",
            name="fixture_bracket_advancement_valid",
        ),
        Index(
            "ix_fixture_bracket_source",
            "source_fixture_id",
        ),
    )


class VenueAvailability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fixture_venue_availability"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    venue_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("venues.id", ondelete="RESTRICT"),
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    __table_args__ = (
        CheckConstraint(
            "end_at > start_at",
            name="fixture_venue_availability_window_valid",
        ),
        Index(
            "ix_fixture_venue_availability_lookup",
            "venue_id",
            "start_at",
            "end_at",
        ),
    )


class SchedulingConstraint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fixture_scheduling_constraints"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "name",
            name="uq_fixture_constraint_tournament_name",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="fixture_constraint_name_not_blank",
        ),
    )


class FixtureChangeAudit(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fixture_change_audits"

    fixture_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fixtures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160))
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    __table_args__ = (
        Index(
            "ix_fixture_change_audits_fixture_created",
            "fixture_id",
            "created_at",
        ),
    )


__all__ = [
    "FixtureGenerationRun",
    "FixtureRound",
    "Fixture",
    "FixtureBracketDependency",
    "VenueAvailability",
    "SchedulingConstraint",
    "FixtureChangeAudit",
]
