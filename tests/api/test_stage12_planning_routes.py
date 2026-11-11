from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.fixture_planning import router
from app.db.session import get_db_session
from app.services.fixture import FixtureConflictError, FixtureValidationError
from app.services.fixture_planning import FixturePlanningService


@pytest.fixture
def database():
    session = MagicMock()
    session.commit, session.rollback = AsyncMock(), AsyncMock()
    return session


@pytest.fixture
async def client(database):
    app = FastAPI()
    app.include_router(router)
    async def session():
        yield database
    app.dependency_overrides[get_db_session] = session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_preview_never_commits(client, database, monkeypatch):
    preview = AsyncMock(return_value={"valid": True, "fixtures": []})
    monkeypatch.setattr(FixturePlanningService, "preview", preview)
    response = await client.post(f"/fixtures/tournaments/{uuid4()}/generate-preview", json={"method": "round_robin"})
    assert response.status_code == 200
    database.commit.assert_not_awaited()


async def test_draft_save_requires_an_idempotency_key(client, database):
    response = await client.post(f"/fixtures/tournaments/{uuid4()}/plans", json={"method": "round_robin"})
    assert response.status_code == 422
    database.commit.assert_not_awaited()


async def test_publish_commits_once(client, database, monkeypatch):
    monkeypatch.setattr(FixturePlanningService, "publish", AsyncMock(return_value={"published_count": 3, "created_match_count": 2}))
    response = await client.post(f"/fixtures/generations/{uuid4()}/confirm", json={"expected_versions": {str(uuid4()): 1}})
    assert response.status_code == 200
    assert response.json()["created_match_count"] == 2
    database.commit.assert_awaited_once()


@pytest.mark.parametrize("error, status", [(FixtureValidationError("Venue conflict"), 422), (FixtureConflictError("Version changed"), 409), (RuntimeError("Partial match failure"), None)])
async def test_failed_publication_rolls_back_everything(client, database, monkeypatch, error, status):
    monkeypatch.setattr(FixturePlanningService, "publish", AsyncMock(side_effect=error))
    async def request():
        return await client.post(f"/fixtures/generations/{uuid4()}/confirm", json={"expected_versions": {str(uuid4()): 1}})
    if status is None:
        with pytest.raises(RuntimeError):
            await request()
    else:
        response = await request()
        assert response.status_code == status
    database.commit.assert_not_awaited()
    database.rollback.assert_awaited_once()


async def test_reschedule_rejects_naive_times_before_service(client, database):
    response = await client.post(f"/fixtures/{uuid4()}/actions", json={"action": "reschedule", "expected_version": 1,
        "reason": "Rain", "scheduled_at": "2026-11-20T10:00:00", "ends_at": "2026-11-20T13:00:00", "venue_id": str(uuid4())})
    assert response.status_code == 422
    database.commit.assert_not_awaited()
