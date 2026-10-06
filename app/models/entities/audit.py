from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    AuditAction,
    db_enum,
)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    action: Mapped[AuditAction] = mapped_column(db_enum(AuditAction, "audit_action"), nullable=False)
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


__all__ = ["AuditLog"]
