from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import create_app


async def request_health(session: AsyncSession):
    app = create_app()
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health")



@pytest.mark.asyncio
async def test_health_route_returns_200_when_database_is_available() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 1

    response = await request_health(session)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert (response.json()["database"]["status"] == "ok")



@pytest.mark.asyncio
async def test_health_route_returns_503_when_database_is_unavailable() -> None:
    session = AsyncMock(spec=AsyncSession)

    session.scalar.side_effect = SQLAlchemyError("connection failed")
    response = await request_health(session)

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert (response.json()["database"]["status"] == "error")