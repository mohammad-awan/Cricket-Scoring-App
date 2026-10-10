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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    CorrectionType,
    DeliveryStatus,
    WicketType,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.innings import Innings
    from app.models.entities.matches import Match
    from app.models.entities.players import Player


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deliveries"

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
    delivery_number: Mapped[int] = mapped_column(Integer, nullable=False)
    over_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ball_number: Mapped[int] = mapped_column(Integer, nullable=False)
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
    # =========================
    # RUN ATTRIBUTION
    # =========================
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
    wide_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    no_ball_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    bye_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    leg_bye_runs: Mapped[int] = mapped_column(
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
    # =========================
    # WICKET DATA
    # =========================
    wicket_type: Mapped[WicketType | None] = mapped_column(
        db_enum(
            WicketType,
            "wicket_type",
        ),
        nullable=True,
    )
    dismissed_player_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "players.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    fielder_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "players.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    next_batter_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "players.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    # Mainly needed for exact run-out state reconstruction.
    wicket_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        db_enum(
            DeliveryStatus,
            "delivery_status",
        ),
        nullable=False,
        default=DeliveryStatus.RECORDED,
        server_default="recorded",
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        comment=(
            "Nullable until Stage 10 "
            "authentication is implemented."
        ),
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # Client-generated idempotency key for
    # duplicate-submission protection.
    client_event_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    # SHA-256 of the canonical request body, used to
    # tell a genuine retry from a reused key.
    client_event_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # =========================
    # RELATIONSHIPS
    # =========================
    match: Mapped[Match] = relationship(
        "Match",
        back_populates="deliveries",
        lazy="raise_on_sql",
    )
    innings: Mapped[Innings] = relationship(
        "Innings",
        back_populates="deliveries",
        lazy="raise_on_sql",
    )
    striker: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.striker_id
        ],
        lazy="raise_on_sql",
    )
    non_striker: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.non_striker_id
        ],
        lazy="raise_on_sql",
    )
    bowler: Mapped[Player] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.bowler_id
        ],
        lazy="raise_on_sql",
    )
    dismissed_player: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.dismissed_player_id
        ],
        lazy="raise_on_sql",
    )
    fielder: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.fielder_id
        ],
        lazy="raise_on_sql",
    )
    next_batter: Mapped[Player | None] = relationship(
        "Player",
        foreign_keys=lambda: [
            Delivery.next_batter_id
        ],
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
            name=(
                "uq_deliveries_"
                "innings_delivery_number"
            ),
        ),
        UniqueConstraint(
            "match_id",
            "client_event_id",
            name="uq_deliveries_match_client_event",
        ),
        CheckConstraint(
            "delivery_number > 0",
            name=(
                "deliveries_"
                "delivery_number_positive"
            ),
        ),
        CheckConstraint(
            "over_number > 0",
            name=(
                "deliveries_"
                "over_number_positive"
            ),
        ),
        CheckConstraint(
            "ball_number > 0",
            name=(
                "deliveries_"
                "ball_number_positive"
            ),
        ),
        CheckConstraint(
            "batter_runs >= 0 "
            "AND extra_runs >= 0 "
            "AND total_runs >= 0",
            name=(
                "deliveries_"
                "runs_non_negative"
            ),
        ),
        CheckConstraint(
            "wide_runs >= 0 "
            "AND no_ball_runs >= 0 "
            "AND bye_runs >= 0 "
            "AND leg_bye_runs >= 0",
            name=(
                "deliveries_"
                "extra_components_non_negative"
            ),
        ),
        CheckConstraint(
            "extra_runs = "
            "wide_runs + "
            "no_ball_runs + "
            "bye_runs + "
            "leg_bye_runs",
            name=(
                "deliveries_"
                "extra_runs_match_components"
            ),
        ),
        CheckConstraint(
            "total_runs = "
            "batter_runs + extra_runs",
            name=(
                "deliveries_"
                "total_runs_match_components"
            ),
        ),
        CheckConstraint(
            "no_ball_runs IN (0, 1)",
            name=(
                "deliveries_"
                "no_ball_single_penalty"
            ),
        ),
        CheckConstraint(
            "NOT ("
            "wide_runs > 0 "
            "AND ("
            "no_ball_runs > 0 "
            "OR bye_runs > 0 "
            "OR leg_bye_runs > 0 "
            "OR batter_runs > 0"
            ")"
            ")",
            name=(
                "deliveries_"
                "wide_exclusive"
            ),
        ),
        CheckConstraint(
            "NOT ("
            "bye_runs > 0 "
            "AND leg_bye_runs > 0"
            ")",
            name=(
                "deliveries_"
                "bye_types_exclusive"
            ),
        ),
        CheckConstraint(
            "NOT ("
            "(bye_runs > 0 "
            "OR leg_bye_runs > 0) "
            "AND batter_runs > 0"
            ")",
            name=(
                "deliveries_"
                "byes_not_batter_runs"
            ),
        ),
        CheckConstraint(
            "is_legal_ball = "
            "(wide_runs = 0 "
            "AND no_ball_runs = 0)",
            name=(
                "deliveries_"
                "legal_ball_matches_extras"
            ),
        ),
        CheckConstraint(
            "("
            "wicket_type IS NULL "
            "AND dismissed_player_id IS NULL"
            ") "
            "OR "
            "("
            "wicket_type IS NOT NULL "
            "AND dismissed_player_id IS NOT NULL"
            ")",
            name=(
                "deliveries_"
                "wicket_fields_together"
            ),
        ),
        CheckConstraint(
            "wicket_type IS NOT NULL "
            "OR ("
            "fielder_id IS NULL "
            "AND next_batter_id IS NULL"
            ")",
            name=(
                "deliveries_"
                "wicket_dependents_require_wicket"
            ),
        ),
        CheckConstraint(
            "wicket_end IS NULL "
            "OR wicket_end IN "
            "('striker_end', 'non_striker_end')",
            name=(
                "deliveries_"
                "wicket_end_valid"
            ),
        ),
        CheckConstraint(
            "wicket_end IS NULL "
            "OR wicket_type = 'run_out'",
            name=(
                "deliveries_"
                "wicket_end_requires_run_out"
            ),
        ),
        CheckConstraint(
            "striker_id <> non_striker_id",
            name=(
                "deliveries_"
                "batters_must_differ"
            ),
        ),
        Index(
            "ix_deliveries_match_id",
            "match_id",
        ),
        Index(
            "ix_deliveries_innings_id",
            "innings_id",
        ),
        Index(
            "ix_deliveries_"
            "match_innings_sequence",
            "match_id",
            "innings_id",
            "delivery_number",
        ),
        Index(
            "ix_deliveries_"
            "innings_status",
            "innings_id",
            "status",
        ),
        Index(
            "ix_deliveries_"
            "dismissed_player_id",
            "dismissed_player_id",
        ),
        Index(
            "ix_deliveries_wicket_type",
            "wicket_type",
        ),
    )


class DeliveryCorrection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "delivery_corrections"

    delivery_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="CASCADE"),
        nullable=False,
    )
    correction_type: Mapped[CorrectionType] = mapped_column(db_enum(CorrectionType, "correction_type"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
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


__all__ = ["Delivery", "DeliveryCorrection"]
