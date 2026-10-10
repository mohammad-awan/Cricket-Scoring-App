from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, status
from app.api.dependencies import QueryDependency, SessionDependency
from app.schemas.common import PageResponse
from app.schemas.venues import VenueCreate, VenueRead, VenueUpdate
from app.services.venues import archive_venue, create_venue, get_venue, list_venues, update_venue


router = APIRouter(prefix="/venues", tags=["venues"])


@router.post("", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
async def create_venue_endpoint(payload: VenueCreate, session: SessionDependency) -> VenueRead:
    return await create_venue(session, payload)


@router.get("", response_model=PageResponse[VenueRead])
async def list_venues_endpoint(query: QueryDependency, session: SessionDependency) -> PageResponse[VenueRead]:
    return await list_venues(session, query)


@router.get("/{venue_id}", response_model=VenueRead)
async def get_venue_endpoint(venue_id: UUID, session: SessionDependency) -> VenueRead:
    return await get_venue(session, venue_id)


@router.patch("/{venue_id}", response_model=VenueRead)
async def update_venue_endpoint(
    venue_id: UUID,
    payload: VenueUpdate,
    session: SessionDependency,
) -> VenueRead:
    return await update_venue(session, venue_id, payload)


@router.post("/{venue_id}/archive", response_model=VenueRead)
async def archive_venue_endpoint(venue_id: UUID, session: SessionDependency) -> VenueRead:
    return await archive_venue(session, venue_id)
