from __future__ import annotations
from typing import TYPE_CHECKING
from sqlalchemy import (
    CheckConstraint,
    Index,
    Integer,
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
    VenueStatus,
    db_enum,
)

if TYPE_CHECKING:
    from app.models.entities.matches import Match


class Venue(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


__all__ = ["Venue"]
