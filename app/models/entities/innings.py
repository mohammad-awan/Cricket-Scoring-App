from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    InningsStatus,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.matches import Match
    from app.models.entities.players import Player
    from app.models.entities.scoring import Delivery
    from app.models.entities.teams import Team


class Innings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "innings"

    match_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
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


__all__ = ["Innings"]
