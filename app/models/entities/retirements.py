from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
    DeliveryStatus,
    RetirementType,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.players import Player


class BatterRetirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A batter leaving the crease between deliveries.

    Retirements are immutable innings events. They are
    replayed together with deliveries: each one is
    anchored after a delivery number and stores the
    crease before and after, so reconstruction never
    depends on mutable innings caches.

    Correction voids the row instead of deleting it.
    """

    __tablename__ = "batter_retirements"

    match_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    innings_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("innings.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Permanent per-innings ordinal, never reused after a void.
    event_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Last official delivery_number when the event happened
    # (0 = before the first ball).
    after_delivery_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    retirement_type: Mapped[RetirementType] = mapped_column(
        db_enum(RetirementType, "retirement_type"),
        nullable=False,
    )
    # NULL only when retired out was the final wicket.
    replacement_player_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=True,
    )
    selection_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    striker_before_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    non_striker_before_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    striker_after_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    non_striker_after_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        db_enum(DeliveryStatus, "delivery_status"),
        nullable=False,
        default=DeliveryStatus.RECORDED,
        server_default="recorded",
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        comment="Nullable until Stage 10 authentication is implemented.",
    )

    player: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [BatterRetirement.player_id],
        lazy="raise_on_sql",
    )
    replacement_player: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [BatterRetirement.replacement_player_id],
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "innings_id",
            "event_number",
            name="uq_batter_retirements_innings_event_number",
        ),
        CheckConstraint(
            "event_number > 0",
            name="batter_retirements_event_number_positive",
        ),
        CheckConstraint(
            "after_delivery_number >= 0",
            name="batter_retirements_after_delivery_non_negative",
        ),
        CheckConstraint(
            "selection_mode IN ('automatic', 'manual')",
            name="batter_retirements_selection_mode_valid",
        ),
        CheckConstraint(
            "striker_before_id <> non_striker_before_id "
            "AND striker_after_id <> non_striker_after_id",
            name="batter_retirements_batters_must_differ",
        ),
        CheckConstraint(
            "replacement_player_id IS NOT NULL "
            "OR retirement_type = 'retired_out'",
            name="batter_retirements_hurt_requires_replacement",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="batter_retirements_reason_not_blank",
        ),
        CheckConstraint(
            "(status = 'recorded' AND void_reason IS NULL AND voided_at IS NULL) "
            "OR (status = 'void' AND void_reason IS NOT NULL AND voided_at IS NOT NULL)",
            name="batter_retirements_void_fields_together",
        ),
        Index("ix_batter_retirements_match_id", "match_id"),
        Index("ix_batter_retirements_innings_status", "innings_id", "status"),
        Index("ix_batter_retirements_player_id", "player_id"),
    )


__all__ = ["BatterRetirement"]
