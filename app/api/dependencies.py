from __future__ import annotations
from typing import Annotated
from fastapi import Query
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