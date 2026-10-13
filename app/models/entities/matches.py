from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    MatchStatus,
    MatchType,
    PlayerRole,
    TossDecision,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.innings import Innings
    from app.models.entities.players import Player
    from app.models.entities.scoring import Delivery
    from app.models.entities.teams import Team
    from app.models.entities.tournaments import Tournament
    from app.models.entities.venues import Venue


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matches"

    title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    match_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    total_overs: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    tournament_ruleset_id: Mapped[UUID | None] = (
        mapped_column(
            PostgreSQLUUID(as_uuid=True),
            ForeignKey(
                "tournament_rule_sets.id",
                ondelete="RESTRICT",
            ),
            nullable=True,
        )
    )
    effective_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    effective_rules_checksum: Mapped[str | None] = (
        mapped_column(
            String(64),
            nullable=True,
        )
    )
    rules_locked_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
            nullable=True,
        )
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    toss_decision: Mapped[TossDecision | None] = mapped_column(db_enum(TossDecision, "toss_decision"), nullable=True)
    winner_team_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result_margin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    winner_team: Mapped[Team | None] = relationship(
        "Team",
        foreign_keys=lambda: [Match.winner_team_id],
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
    deliveries: Mapped[list[Delivery]] = relationship(
        "Delivery",
        back_populates="match",
        passive_deletes=True,
        lazy="raise_on_sql",
        order_by="Delivery.delivery_number",
    )

    __table_args__ = (
        CheckConstraint(
            "team_a_id <> team_b_id",
            name="matches_teams_must_differ",
        ),
        CheckConstraint(
            "(tournament_ruleset_id IS NULL AND effective_rules IS NULL "
            "AND effective_rules_checksum IS NULL AND rules_locked_at IS NULL) "
            "OR (tournament_ruleset_id IS NOT NULL AND effective_rules IS NOT NULL "
            "AND effective_rules_checksum IS NOT NULL AND rules_locked_at IS NOT NULL)",
            name="matches_rule_snapshot_complete",
        ),
        Index("ix_matches_tournament_ruleset_id", "tournament_ruleset_id"),
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
        CheckConstraint(
            (
                "result_type IS NULL "
                "OR result_type IN "
                "('runs', 'wickets', 'tie')"
            ),
            name="matches_result_type_valid",
        ),
        CheckConstraint(
            (
                "result_margin IS NULL "
                "OR result_margin >= 0"
            ),
            name=(
                "matches_result_margin_"
                "non_negative"
            ),
        ),
        CheckConstraint(
            (
                "("
                "result_type IS NULL "
                "AND result_margin IS NULL"
                ") "
                "OR "
                "("
                "result_type = 'tie' "
                "AND result_margin = 0"
                ") "
                "OR "
                "("
                "result_type IN "
                "('runs', 'wickets') "
                "AND result_margin > 0"
                ")"
            ),
            name="matches_result_fields_valid",
        ),
        Index("ix_matches_status", "status"),
        Index("ix_matches_scheduled_at", "scheduled_at"),
        Index("ix_matches_team_a_id", "team_a_id"),
        Index("ix_matches_team_b_id", "team_b_id"),
        Index("ix_matches_winner_team_id", "winner_team_id"),
        Index("ix_matches_completed_at", "completed_at")
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
    batting_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    team: Mapped[Team] = relationship("Team", lazy="raise_on_sql")
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


__all__ = ["Match", "MatchPlayer"]
