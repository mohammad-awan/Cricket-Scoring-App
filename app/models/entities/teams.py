from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import PlayerRole, TeamStatus, db_enum

if TYPE_CHECKING:
    from app.models.entities.matches import Match
    from app.models.entities.players import Player


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
        foreign_keys="Match.team_a_id",
        back_populates="team_a",
        lazy="raise_on_sql",
    )
    away_matches: Mapped[list[Match]] = relationship(
        "Match",
        foreign_keys="Match.team_b_id",
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
    squad_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    joined_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)
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


__all__ = ["Team", "TeamPlayer"]
