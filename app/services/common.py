from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models import AuditAction, AuditLog


@asynccontextmanager
async def service_transaction(session: AsyncSession) -> AsyncIterator[None]:
    if session.in_transaction():
        yield
        return

    async with session.begin():
        yield


def integrity_conflict(error: IntegrityError, resource: str) -> ConflictError:
    return ConflictError(
        f"{resource} conflicts with existing data "
        "or violates a data constraint."
    )


def add_audit_log(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: Any,
    action: AuditAction,
    details: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=None,
            details=details,
        )
    )