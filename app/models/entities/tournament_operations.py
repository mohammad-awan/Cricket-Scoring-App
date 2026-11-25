
from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDPrimaryKeyMixin



class TournamentAward(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tournament_awards"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    award_code: Mapped[str] = mapped_column(String(60), nullable=False)
    player_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    selection_method: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confirmed_by: Mapped[str | None] = mapped_column(String(160))
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "award_code",
            name="uq_tournament_award_code",
        ),
        CheckConstraint(
            "status IN ('confirmed', 'revoked')",
            name="ck_tournament_award_status",
        ),
        CheckConstraint(
            "selection_method IN ('manual', 'statistical')",
            name="ck_tournament_award_method",
        ),
        CheckConstraint(
            "(player_id IS NOT NULL) <> (team_id IS NOT NULL)",
            name="ck_tournament_award_recipient",
        ),
    )


class TournamentCloseout(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tournament_closeouts"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    champion_team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_frozen: Mapped[bool] = mapped_column(nullable=False, default=True)
    finalized_by: Mapped[str | None] = mapped_column(String(160))
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(Text)


class TournamentDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tournament_decisions"

    tournament_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    actor_id: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
