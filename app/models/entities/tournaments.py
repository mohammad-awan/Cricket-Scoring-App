from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING
from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    TournamentStatus,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.matches import Match


class Tournament(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "tournaments"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    season: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("ix_tournaments_status", "status"),
        Index("ix_tournaments_name", "name"),
        Index("ix_tournaments_season", "season"),
    )


__all__ = ["Tournament"]
