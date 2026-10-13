from __future__ import annotations
import hmac
from typing import Annotated
from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.exceptions import PermissionDeniedError
from app.db.session import get_db_session
from app.schemas.common import MasterDataQuery



def get_master_data_query(
    page: Annotated[
        int,
        Query(
            ge=1,
            description="One-based page number",
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Number of records per page",
        ),
    ] = 20,
    search: Annotated[
        str | None,
        Query(max_length=100),
    ] = None,
    include_archived: bool = False,
) -> MasterDataQuery:
    return MasterDataQuery(
        page=page,
        page_size=page_size,
        search=(
            search.strip()
            if search and search.strip()
            else None
        ),
        include_archived=include_archived,
    )


SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
QueryDependency = Annotated[MasterDataQuery, Depends(get_master_data_query)]


def require_organizer(
    x_organizer_token: Annotated[
        str | None,
        Header(description="Tournament organizer token"),
    ] = None,
) -> str | None:
    """Interim organizer guard for privileged tournament endpoints.

    Returns the actor id recorded in tournament audit events. Replace
    with real user authentication and per-tournament ownership checks.
    """

    settings = get_settings()
    expected = settings.organizer_api_token

    if expected is None:
        if settings.environment in {"development", "test"}:
            return None

        raise PermissionDeniedError(
            "Organizer authorization is not configured"
        )

    if x_organizer_token is None or not hmac.compare_digest(
        x_organizer_token.encode("utf-8"),
        expected.get_secret_value().encode("utf-8"),
    ):
        raise PermissionDeniedError("Organizer authorization required")

    return "organizer"


OrganizerDependency = Annotated[str | None, Depends(require_organizer)]
