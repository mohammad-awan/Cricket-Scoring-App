from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING
from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import PlayerStatus, db_enum

if TYPE_CHECKING:
    from app.models.entities.matches import MatchPlayer
    from app.models.entities.teams import TeamPlayer


class Player(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "players"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
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


__all__ = ["Player"]
