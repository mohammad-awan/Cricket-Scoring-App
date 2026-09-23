from __future__ import annotations
from datetime import date, datetime
from typing import Any
from uuid import UUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    AuditAction,
    CorrectionType,
    DeliveryStatus,
    InningsStatus,
    MatchStatus,
    MatchType,
    PlayerRole,
    PlayerStatus,
    TeamStatus,
    TossDecision,
    TournamentStatus,
    VenueStatus,
    db_enum,
)


class Team(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
    )
    short_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
    )
    country: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    status: Mapped[TeamStatus] = mapped_column(
        db_enum(TeamStatus, "team_status"),
        nullable=False,
        default=TeamStatus.ACTIVE,
        server_default="active",
    )

    players: Mapped[list[TeamPlayer]] = relationship(
        "TeamPlayer",
        back_populates="team",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
    )

    home_matches: Mapped[list[Match]] = relationship(
        "Match",
        foreign_keys=lambda: [Match.team_a_id],
        back_populates="team_a",
        lazy="raise_on_sql",
    )

    away_matches: Mapped[list[Match]] = relationship(
        "Match",
        foreign_keys=lambda: [Match.team_b_id],
        back_populates="team_b",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="team_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(short_name)) > 0",
            name="team_short_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(code)) > 0",
            name="team_code_not_blank",
        ),
        Index("ix_teams_status", "status"),
        Index("ix_teams_name", "name"),
    )


class Player(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "players"

    full_name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    short_name: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    nationality: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    external_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        unique=True,
    )
    status: Mapped[PlayerStatus] = mapped_column(
        db_enum(PlayerStatus, "player_status"),
        nullable=False,
        default=PlayerStatus.ACTIVE,
        server_default="active",
    )

    teams: Mapped[list[TeamPlayer]] = relationship(
        "TeamPlayer",
        back_populates="player",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
    )

    match_selections: Mapped[list[MatchPlayer]] = relationship(
        "MatchPlayer",
        back_populates="player",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(full_name)) > 0",
            name="player_full_name_not_blank",
        ),
        UniqueConstraint(
            "full_name",
            "date_of_birth",
            name="uq_players_full_name_date_of_birth",
        ),
        Index("ix_players_status", "status"),
        Index("ix_players_full_name", "full_name"),
    )


class TeamPlayer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_players"

    team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    player_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[PlayerRole] = mapped_column(
        db_enum(PlayerRole, "player_role"),
        nullable=False,
        default=PlayerRole.BATTER,
        server_default="batter",
    )
    squad_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    joined_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    left_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    team: Mapped[Team] = relationship(
        "Team",
        back_populates="players",
        lazy="raise_on_sql",
    )

    player: Mapped[Player] = relationship(
        "Player",
        back_populates="teams",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "player_id",
            name="uq_team_players_team_player",
        ),
        CheckConstraint(
            "squad_number IS NULL OR squad_number > 0",
            name="team_players_squad_number_positive",
        ),
        CheckConstraint(
            "left_on IS NULL OR joined_on IS NULL OR left_on >= joined_on",
            name="team_players_dates_valid",
        ),
        Index("ix_team_players_team_id", "team_id"),
        Index("ix_team_players_player_id", "player_id"),
    )


class Venue(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    country: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    capacity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[VenueStatus] = mapped_column(
        db_enum(VenueStatus, "venue_status"),
        nullable=False,
        default=VenueStatus.ACTIVE,
        server_default="active",
    )

    matches: Mapped[list[Match]] = relationship(
        "Match",
        back_populates="venue",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            "city",
            name="uq_venues_name_city",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="venue_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(city)) > 0",
            name="venue_city_not_blank",
        ),
        CheckConstraint(
            "capacity IS NULL OR capacity >= 0",
            name="venue_capacity_non_negative",
        ),
        Index("ix_venues_status", "status"),
        Index("ix_venues_name", "name"),
        Index("ix_venues_city", "city"),
    )


class Tournament(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "tournaments"

    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        unique=True,
    )
    season: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    organizer: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
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
        Index("ix_tournaments_status", "status"),
        Index("ix_tournaments_name", "name"),
        Index("ix_tournaments_season", "season"),
    )


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matches"

    title: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    match_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    team_a_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_b_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tournament_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="SET NULL"),
        nullable=True,
    )
    venue_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("venues.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_type: Mapped[MatchType] = mapped_column(
        db_enum(MatchType, "match_type"),
        nullable=False,
        default=MatchType.T20,
        server_default="t20",
    )
    players_per_side: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=11,
        server_default="11",
    )
    total_overs: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    balls_per_over: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=6,
        server_default="6",
    )
    innings_per_team: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[MatchStatus] = mapped_column(
        db_enum(MatchStatus, "match_status"),
        nullable=False,
        default=MatchStatus.DRAFT,
        server_default="draft",
    )
    toss_winner_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    toss_decision: Mapped[TossDecision | None] = mapped_column(
        db_enum(TossDecision, "toss_decision"),
        nullable=True,
    )

    team_a: Mapped[Team] = relationship(
        "Team",
        foreign_keys=lambda: [Match.team_a_id],
        back_populates="home_matches",
        lazy="raise_on_sql",
    )

    team_b: Mapped[Team] = relationship(
        "Team",
        foreign_keys=lambda: [Match.team_b_id],
        back_populates="away_matches",
        lazy="raise_on_sql",
    )

    tournament: Mapped[Tournament | None] = relationship(
        "Tournament",
        back_populates="matches",
        lazy="raise_on_sql",
    )

    venue: Mapped[Venue | None] = relationship(
        "Venue",
        back_populates="matches",
        lazy="raise_on_sql",
    )

    toss_winner: Mapped[Team | None] = relationship(
        "Team",
        foreign_keys=lambda: [Match.toss_winner_id],
        lazy="raise_on_sql",
    )

    players: Mapped[list[MatchPlayer]] = relationship(
        "MatchPlayer",
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
    )

    innings: Mapped[list[Innings]] = relationship(
        "Innings",
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
        order_by="Innings.innings_number",
    )

    __table_args__ = (
        CheckConstraint(
            "team_a_id <> team_b_id",
            name="matches_teams_must_differ",
        ),
        CheckConstraint(
            "total_overs IS NULL OR total_overs > 0",
            name="matches_total_overs_positive_when_set",
        ),
        CheckConstraint(
            "players_per_side >= 2",
            name="matches_players_per_side_minimum",
        ),
        CheckConstraint(
            "balls_per_over > 0",
            name="matches_balls_per_over_positive",
        ),
        CheckConstraint(
            "innings_per_team > 0",
            name="matches_innings_per_team_positive",
        ),
        CheckConstraint(
            "match_number IS NULL OR match_number > 0",
            name="matches_match_number_positive",
        ),
        CheckConstraint(
            "(toss_winner_id IS NULL AND toss_decision IS NULL) OR "
            "(toss_winner_id IS NOT NULL AND toss_decision IS NOT NULL)",
            name="matches_toss_fields_together",
        ),
        Index("ix_matches_status", "status"),
        Index("ix_matches_scheduled_at", "scheduled_at"),
        Index("ix_matches_team_a_id", "team_a_id"),
        Index("ix_matches_team_b_id", "team_b_id"),
    )


class MatchPlayer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "match_players"

    match_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    player_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batting_order: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    role: Mapped[PlayerRole] = mapped_column(
        db_enum(PlayerRole, "player_role"),
        nullable=False,
        default=PlayerRole.BATTER,
        server_default="batter",
    )
    is_captain: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_wicket_keeper: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    match: Mapped[Match] = relationship(
        "Match",
        back_populates="players",
        lazy="raise_on_sql",
    )

    team: Mapped[Team] = relationship(
        "Team",
        lazy="raise_on_sql",
    )

    player: Mapped[Player] = relationship(
        "Player",
        back_populates="match_selections",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "player_id",
            name="uq_match_players_match_player",
        ),
        UniqueConstraint(
            "match_id",
            "team_id",
            "batting_order",
            name="uq_match_players_batting_order",
        ),
        CheckConstraint(
            "batting_order IS NULL OR batting_order > 0",
            name="match_players_batting_order_positive",
        ),
        Index("ix_match_players_match_id", "match_id"),
        Index("ix_match_players_team_id", "team_id"),
        Index("ix_match_players_player_id", "player_id"),
    )


class Innings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "innings"

    match_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    innings_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    batting_team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bowling_team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[InningsStatus] = mapped_column(
        db_enum(InningsStatus, "innings_status"),
        nullable=False,
        default=InningsStatus.PENDING,
        server_default="pending",
    )
    total_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    wickets: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    legal_balls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    striker_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    non_striker_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_bowler_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    match: Mapped[Match] = relationship(
        "Match",
        back_populates="innings",
        lazy="raise_on_sql",
    )

    batting_team: Mapped[Team] = relationship(
        "Team",
        foreign_keys=lambda: [Innings.batting_team_id],
        lazy="raise_on_sql",
    )

    bowling_team: Mapped[Team] = relationship(
        "Team",
        foreign_keys=lambda: [Innings.bowling_team_id],
        lazy="raise_on_sql",
    )

    striker: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [Innings.striker_id],
        lazy="raise_on_sql",
    )

    non_striker: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [Innings.non_striker_id],
        lazy="raise_on_sql",
    )

    current_bowler: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [Innings.current_bowler_id],
        lazy="raise_on_sql",
    )

    deliveries: Mapped[list[Delivery]] = relationship(
        "Delivery",
        back_populates="innings",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
        order_by="Delivery.delivery_number",
    )

    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "innings_number",
            name="uq_innings_match_number",
        ),
        CheckConstraint(
            "innings_number > 0",
            name="innings_number_positive",
        ),
        CheckConstraint(
            "batting_team_id <> bowling_team_id",
            name="innings_teams_must_differ",
        ),
        CheckConstraint(
            "total_runs >= 0",
            name="innings_total_runs_non_negative",
        ),
        CheckConstraint(
            "wickets >= 0",
            name="innings_wickets_non_negative",
        ),
        CheckConstraint(
            "legal_balls >= 0",
            name="innings_legal_balls_non_negative",
        ),
        CheckConstraint(
            "striker_id IS NULL OR non_striker_id IS NULL OR striker_id <> non_striker_id",
            name="innings_batters_must_differ",
        ),
        Index("ix_innings_match_id", "match_id"),
        Index("ix_innings_status", "status"),
    )


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deliveries"

    innings_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("innings.id", ondelete="CASCADE"),
        nullable=False,
    )
    delivery_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    over_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    ball_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    striker_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    non_striker_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bowler_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batter_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    extra_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_legal_ball: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        db_enum(DeliveryStatus, "delivery_status"),
        nullable=False,
        default=DeliveryStatus.RECORDED,
        server_default="recorded",
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        comment="Nullable until Stage 10 authentication is implemented.",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    innings: Mapped[Innings] = relationship(
        "Innings",
        back_populates="deliveries",
        lazy="raise_on_sql",
    )

    striker: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [Delivery.striker_id],
        lazy="raise_on_sql",
    )

    non_striker: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [Delivery.non_striker_id],
        lazy="raise_on_sql",
    )

    bowler: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [Delivery.bowler_id],
        lazy="raise_on_sql",
    )

    corrections: Mapped[list[DeliveryCorrection]] = relationship(
        "DeliveryCorrection",
        back_populates="delivery",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "innings_id",
            "delivery_number",
            name="uq_deliveries_innings_delivery_number",
        ),
        CheckConstraint(
            "delivery_number > 0",
            name="deliveries_delivery_number_positive",
        ),
        CheckConstraint(
            "over_number > 0",
            name="deliveries_over_number_positive",
        ),
        CheckConstraint(
            "ball_number > 0",
            name="deliveries_ball_number_positive",
        ),
        CheckConstraint(
            "batter_runs >= 0 AND extra_runs >= 0 AND total_runs >= 0",
            name="deliveries_runs_non_negative",
        ),
        CheckConstraint(
            "total_runs = batter_runs + extra_runs",
            name="deliveries_total_runs_match_components",
        ),
        CheckConstraint(
            "striker_id <> non_striker_id",
            name="deliveries_batters_must_differ",
        ),
        Index("ix_deliveries_innings_id", "innings_id"),
        Index(
            "ix_deliveries_innings_status",
            "innings_id",
            "status",
        ),
    )



class DeliveryCorrection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "delivery_corrections"

    delivery_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="CASCADE"),
        nullable=False,
    )
    correction_type: Mapped[CorrectionType] = mapped_column(
        db_enum(CorrectionType, "correction_type"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        comment="Nullable until Stage 10 authentication is implemented.",
    )

    delivery: Mapped[Delivery] = relationship(
        "Delivery",
        back_populates="corrections",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="delivery_corrections_reason_not_blank",
        ),
        Index(
            "ix_delivery_corrections_delivery_id",
            "delivery_id",
        ),
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    entity_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    action: Mapped[AuditAction] = mapped_column(
        db_enum(AuditAction, "audit_action"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        comment="Nullable until Stage 10 authentication is implemented.",
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="audit_logs_entity_type_not_blank",
        ),
        Index(
            "ix_audit_logs_entity",
            "entity_type",
            "entity_id",
        ),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


__all__ = [
    "AuditLog",
    "Delivery",
    "DeliveryCorrection",
    "Innings",
    "Match",
    "MatchPlayer",
    "Player",
    "Team",
    "TeamPlayer",
    "Tournament",
    "Venue",
]