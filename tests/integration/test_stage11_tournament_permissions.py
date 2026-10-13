"""Organizer guard on Stage 11 tournament mutations.

These requests are rejected before any database access, so they run
without RUN_LIVE_DB_TESTS.
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import dependencies
from app.db.session import get_db_session
from app.main import create_app


def _settings(environment: str, token: str | None):
    return SimpleNamespace(
        environment=environment,
        organizer_api_token=SecretStr(token) if token else None,
    )


async def _post(monkeypatch, settings, path: str, json: dict, headers=None):
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)

    session = AsyncMock(spec=AsyncSession)
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(path, json=json, headers=headers or {})

    return response, session


MUTATIONS = [
    ("/tournaments/{id}/rules", {"rules": {}}),
    ("/tournaments/{id}/transitions", {"target_status": "scheduled"}),
    ("/tournaments/{id}/publication", {"publish": True}),
    ("/tournaments/{id}/teams", {"team_id": str(uuid4())}),
    ("/tournaments/{id}/rosters/lock", {}),
    ("/tournaments/{id}/groups", {"name": "Group A"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "body"), MUTATIONS)
async def test_mutations_require_token_when_configured(monkeypatch, path, body) -> None:
    response, session = await _post(
        monkeypatch,
        _settings("production", "s3cret"),
        path.format(id=uuid4()),
        body,
    )

    assert response.status_code == 403
    session.execute.assert_not_called()
    session.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_token_is_rejected(monkeypatch) -> None:
    response, _ = await _post(
        monkeypatch,
        _settings("production", "s3cret"),
        f"/tournaments/{uuid4()}/publication",
        {"publish": True},
        headers={"X-Organizer-Token": "guess"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_production_without_configured_token_is_closed(monkeypatch) -> None:
    response, _ = await _post(
        monkeypatch,
        _settings("production", None),
        f"/tournaments/{uuid4()}/publication",
        {"publish": True},
    )

    assert response.status_code == 403
    assert "not configured" in response.json()["detail"]


def test_require_organizer_accepts_valid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: _settings("production", "s3cret"),
    )

    assert dependencies.require_organizer("s3cret") == "organizer"


def test_development_without_token_is_open(monkeypatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: _settings("development", None),
    )

    assert dependencies.require_organizer(None) is None


@pytest.mark.asyncio
async def test_rule_validation_preview_is_public(monkeypatch) -> None:
    response, _ = await _post(
        monkeypatch,
        _settings("production", "s3cret"),
        "/tournaments/rules/validate",
        {"rules": {"dls_enabled": True}},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
