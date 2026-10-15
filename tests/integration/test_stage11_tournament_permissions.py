
"""Stage 11 tournament public-access integration tests.

No organizer authentication or authorization is required.

Tests exercise real FastAPI routing and dependency injection.
Tournament services are isolated so database behavior is not
mistaken for access-control behavior.

No RUN_LIVE_DB_TESTS configuration is required.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import dependencies
from app.api.routes import tournaments as tournament_routes
from app.db.session import get_db_session
from app.main import create_app


MUTATIONS = [
    (
        "/tournaments/{id}/rules",
        {"rules": {}},
        "create_tournament_rules",
    ),
    (
        "/tournaments/{id}/transitions",
        {"target_status": "scheduled"},
        "change_tournament_status",
    ),
    (
        "/tournaments/{id}/publication",
        {"publish": True},
        "set_tournament_publication",
    ),
    (
        "/tournaments/{id}/teams",
        {"team_id": str(uuid4())},
        "register_tournament_team",
    ),
    (
        "/tournaments/{id}/rosters/lock",
        {},
        "lock_tournament_rosters",
    ),
    (
        "/tournaments/{id}/groups",
        {"name": "Group A"},
        "create_tournament_group",
    ),
]


@pytest.fixture
def app():
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        session = AsyncMock(spec=AsyncSession)
        yield session

    application.dependency_overrides[
        get_db_session
    ] = override_session

    yield application

    application.dependency_overrides.clear()


async def post_json(
    app,
    path: str,
    payload: dict,
    headers: dict | None = None,
):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.post(
            path,
            json=payload,
            headers=headers or {},
        )


def test_organizer_dependency_requires_no_token():
    assert dependencies.require_organizer() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload", "service_name"),
    MUTATIONS,
)
async def test_tournament_mutations_are_public(
    monkeypatch,
    app,
    path,
    payload,
    service_name,
):
    """Verify real routes reach services without credentials."""

    service_mock = AsyncMock(
        side_effect=HTTPException(
            status_code=404,
            detail="Test tournament does not exist",
        )
    )

    monkeypatch.setattr(
        tournament_routes.tournament_services,
        service_name,
        service_mock,
    )

    response = await post_json(
        app,
        path.format(id=uuid4()),
        payload,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == ("Test tournament does not exist")
    service_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_token_does_not_block_public_routes(monkeypatch, app):
    """Irrelevant organizer credentials do not affect access."""

    service_mock = AsyncMock(
        side_effect=HTTPException(
            status_code=404,
            detail="Test tournament does not exist",
        )
    )

    monkeypatch.setattr(
        tournament_routes.tournament_services,
        "set_tournament_publication",
        service_mock,
    )

    response = await post_json(
        app,
        f"/tournaments/{uuid4()}/publication",
        {"publish": True},
        headers={
            "X-Organizer-Token": "invalid-token",
        },
    )

    assert response.status_code == 404
    service_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_rule_validation_preview_is_public(app):
    """Public rule preview must enforce cricket capabilities."""

    response = await post_json(
        app,
        "/tournaments/rules/validate",
        {
            "rules": {
                "dls_enabled": True,
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False


@pytest.mark.asyncio
async def test_unsupported_break_rule_is_rejected(app):
    """Unsupported scoring options cannot be activated."""

    response = await post_json(
        app,
        "/tournaments/rules/validate",
        {
            "rules": {
                "mandatory_break_minutes": 15,
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
