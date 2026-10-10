from __future__ import annotations

from contextlib import asynccontextmanager
from math import ceil
from typing import TYPE_CHECKING, Any, AsyncIterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models import AuditAction, AuditLog
from app.schemas.common import MasterDataQuery, PageResponse

if TYPE_CHECKING:
    from app.repositories.base_master_data import MasterDataRepository


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


def duplicate_conflict(resource: str, field: str) -> ConflictError:
    return ConflictError(f"A {resource} with the same {field} already exists.")


async def list_master_data(
    repository: MasterDataRepository[Any],
    query: MasterDataQuery,
    schema: type[Any],
) -> PageResponse[Any]:
    items = await repository.list_page(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        include_archived=query.include_archived,
    )

    total = await repository.count(
        search=query.search,
        include_archived=query.include_archived,
    )

    return PageResponse[schema](  # type: ignore[valid-type]
        items=items,
        page=query.page,
        page_size=query.page_size,
        total=total,
        pages=ceil(total / query.page_size) if total else 0,
    )
