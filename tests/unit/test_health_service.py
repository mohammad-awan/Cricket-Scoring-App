import pytest
from unittest.mock import AsyncMock
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.health import check_health


@pytest.mark.asyncio
async def test_health_service_reports_healthy_database() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 1
    result = await check_health(session)
    assert result.status == "ok"
    assert result.api.status == "ok"
    assert result.database.status == "ok"


@pytest.mark.asyncio
async def test_health_service_hides_database_error_details() -> None:
    session = AsyncMock(spec=AsyncSession)

    session.scalar.side_effect = SQLAlchemyError("secret connection details")
    result = await check_health(session)
    assert result.status == "degraded"
    assert result.database.status == "error"
    assert "secret" not in result.database.detail

