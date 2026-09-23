from typing import Annotated
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.schemas.health import HealthResponse
from app.services.health import check_health


router = APIRouter(tags=["health"])



@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse
        }
    },
)
async def health_check(session: Annotated[AsyncSession, Depends(get_db_session)]) -> HealthResponse | JSONResponse:
    result = await check_health(session)
    if result.status == "degraded":
        return JSONResponse(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content=result.model_dump(mode="json"),
        )

    return result




