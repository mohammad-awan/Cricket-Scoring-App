from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import (
    ComponentHealth,
    HealthResponse,
)


logger = logging.getLogger(__name__)


async def check_health(session: AsyncSession) -> HealthResponse:

    api_health = ComponentHealth(
        status="ok",
        detail="API is Running",
    )

    try:
        result = await session.scalar(
            text("SELECT 1")
        )

        if result != 1:
            raise SQLAlchemyError(
                "Unexpected database health-check result"
            )

    except SQLAlchemyError:

        logger.exception(
            "Database Health Check Failed"
        )

        return HealthResponse(
            status="degraded",
            api=api_health,
            database=ComponentHealth(
                status="error",
                detail=(
                    "Database connection is unavailable"
                ),
            ),
        )

    return HealthResponse(
        status="ok",
        api=api_health,
        database=ComponentHealth(
            status="ok",
            detail="Database connection is healthy",
        ),
    )