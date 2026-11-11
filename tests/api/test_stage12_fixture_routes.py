from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.fixtures import router
from app.db.session import get_db_session
from app.services.fixture import (
    FixtureConflictError,
    FixtureNotFoundError,
    FixtureValidationError,
)


# ---------------------------------------
# TEST CONFIGURATION
# ---------------------------------------


@pytest.fixture
def session():
    database = MagicMock()
    database.commit = AsyncMock()
    database.rollback = AsyncMock()
    database.get = AsyncMock()
    database.scalar = AsyncMock(return_value=0)
    result = MagicMock()
    result.all.return_value = []
    database.scalars = AsyncMock(return_value=result)

    return database



@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(router)
    async def override_db_session():
        yield session

    app.dependency_overrides[get_db_session] = override_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def valid_generation_data():
    return {
        "method": "round_robin",
        "configuration": {},
        "seed": 42,
    }


def valid_fixture_object():
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=uuid4(),
        tournament_id=uuid4(),
        generation_run_id=uuid4(),
        round_id=uuid4(),
        fixture_number=1,
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        venue_id=None,
        scheduled_at=None,
        ends_at=None,
        notes="Updated fixture",
        status="draft",
        is_locked=False,
        version=2,
        match_id=None,
        published_at=None,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------
# FIXTURE GENERATION
# ---------------------------------------

def test_generate_fixtures_success(client, session):
    tournament_id = uuid4()
    generation_run_id = uuid4()

    result = SimpleNamespace(
        generation_run_id=generation_run_id,
        tournament_id=tournament_id,
        fixture_count=6,
        round_count=3,
    )

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.generate_fixtures = AsyncMock(return_value=result)
        response = client.post(
            f"/fixtures/tournaments/{tournament_id}/generate",
            json=valid_generation_data(),
        )

    assert response.status_code == 201
    data = response.json()
    assert data["generation_run_id"] == str(generation_run_id)
    assert data["tournament_id"] == str(tournament_id)
    assert data["fixture_count"] == 6
    assert data["round_count"] == 3

    service.generate_fixtures.assert_awaited_once_with(
        tournament_id=tournament_id,
        method="round_robin",
        configuration={},
        seed=42,
    )

    session.commit.assert_awaited_once()


def test_generate_rejects_invalid_method(client, session):
    tournament_id = uuid4()

    response = client.post(
        f"/fixtures/tournaments/{tournament_id}/generate",
        json={
            "method": "invalid_method",
        },
    )

    assert response.status_code == 422
    session.commit.assert_not_awaited()


def test_generate_tournament_not_found(client, session):
    tournament_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.generate_fixtures = AsyncMock(side_effect=FixtureNotFoundError("Tournament not found."))

        response = client.post(
            f"/fixtures/tournaments/{tournament_id}/generate",
            json=valid_generation_data(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == ("Tournament not found.")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_generate_validation_error(client, session):
    tournament_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value

        service.generate_fixtures = AsyncMock(
            side_effect=FixtureValidationError(
                "Not enough approved teams."
            )
        )

        response = client.post(
            f"/fixtures/tournaments/{tournament_id}/generate",
            json=valid_generation_data(),
        )

    assert response.status_code == 422
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_generate_conflict(client, session):
    tournament_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.generate_fixtures = AsyncMock(
            side_effect=FixtureConflictError(
                "Generation already exists."
            )
        )

        response = client.post(
            f"/fixtures/tournaments/{tournament_id}/generate",
            json=valid_generation_data(),
        )

    assert response.status_code == 409

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------
# LIST TOURNAMENT FIXTURES
# ---------------------------------------

def test_list_tournament_fixtures_empty(client, session):
    tournament_id = uuid4()

    response = client.get(
        f"/fixtures/tournaments/{tournament_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["tournament_id"] == str(
        tournament_id
    )
    assert data["total"] == 0
    assert data["fixtures"] == []

    session.commit.assert_not_awaited()


def test_list_rejects_invalid_limit(client):
    tournament_id = uuid4()

    response = client.get(
        f"/fixtures/tournaments/{tournament_id}",
        params={
            "limit": 0,
        },
    )

    assert response.status_code == 422


def test_list_rejects_negative_offset(client):
    tournament_id = uuid4()

    response = client.get(
        f"/fixtures/tournaments/{tournament_id}",
        params={
            "offset": -1,
        },
    )

    assert response.status_code == 422


# ---------------------------------------
# GET SINGLE FIXTURE
# ---------------------------------------

def test_get_fixture_success(client, session):
    fixture = valid_fixture_object()

    session.get.return_value = fixture

    response = client.get(
        f"/fixtures/{fixture.id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == str(fixture.id)
    assert data["fixture_number"] == 1
    assert data["version"] == 2
    assert data["status"] == "draft"


def test_get_fixture_not_found(client, session):
    fixture_id = uuid4()

    session.get.return_value = None
    response = client.get(f"/fixtures/{fixture_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Fixture not found."


def test_get_fixture_invalid_uuid(client):
    response = client.get("/fixtures/not-a-valid-uuid")
    assert response.status_code == 422


# ---------------------------------------
# PUBLISH FIXTURE GENERATION
# ---------------------------------------

def test_publish_generation_success(client, session):
    generation_run_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value

        service.publish_generation = AsyncMock(return_value=6)
        response = client.post(
            f"/fixtures/generations/{generation_run_id}/publish",
            json={
                "expected_fixture_count": 6,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["generation_run_id"] == str(generation_run_id)
    assert data["published_count"] == 6
    assert data["status"] == "published"

    service.publish_generation.assert_awaited_once_with(
        generation_run_id=generation_run_id,
        expected_fixture_count=6,
    )

    session.commit.assert_awaited_once()


def test_publish_rejects_zero_count(client, session):
    generation_run_id = uuid4()

    response = client.post(
        f"/fixtures/generations/{generation_run_id}/publish",
        json={
            "expected_fixture_count": 0,
        },
    )

    assert response.status_code == 422
    session.commit.assert_not_awaited()


def test_publish_generation_not_found(client, session):
    generation_run_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value

        service.publish_generation = AsyncMock(
            side_effect=FixtureNotFoundError(
                "Generation not found."
            )
        )

        response = client.post(
            f"/fixtures/generations/{generation_run_id}/publish",
            json={
                "expected_fixture_count": 6,
            },
        )

    assert response.status_code == 404

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_publish_generation_conflict(client, session):
    generation_run_id = uuid4()
    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.publish_generation = AsyncMock(
            side_effect=FixtureConflictError(
                "Fixture count mismatch."
            )
        )

        response = client.post(
            f"/fixtures/generations/{generation_run_id}/publish",
            json={
                "expected_fixture_count": 6,
            },
        )
    assert response.status_code == 409
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------
# UPDATE FIXTURE
# ---------------------------------------

def test_update_fixture_success(client, session):
    fixture = valid_fixture_object()
    session.get.return_value = fixture

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.update_fixture = AsyncMock()
        response = client.patch(
            f"/fixtures/{fixture.id}",
            json={
                "expected_version": 1,
                "notes": "Updated fixture",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(fixture.id)
    assert data["version"] == 2
    assert data["notes"] == "Updated fixture"
    service.update_fixture.assert_awaited_once_with(
        fixture_id=fixture.id,
        expected_version=1,
        changes={
            "notes": "Updated fixture",
        },
    )
    session.commit.assert_awaited_once()


def test_update_requires_version(client, session):
    fixture_id = uuid4()

    response = client.patch(
        f"/fixtures/{fixture_id}",
        json={
            "notes": "Updated fixture",
        },
    )

    assert response.status_code == 422

    session.commit.assert_not_awaited()


def test_update_rejects_invalid_version(client):
    fixture_id = uuid4()

    response = client.patch(
        f"/fixtures/{fixture_id}",
        json={
            "expected_version": 0,
            "notes": "Updated fixture",
        },
    )

    assert response.status_code == 422


def test_update_requires_changes(client):
    fixture_id = uuid4()

    response = client.patch(
        f"/fixtures/{fixture_id}",
        json={
            "expected_version": 1,
        },
    )

    assert response.status_code == 422


def test_update_fixture_not_found(client, session):
    fixture_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.update_fixture = AsyncMock(
            side_effect=FixtureNotFoundError(
                "Fixture not found."
            )
        )

        response = client.patch(
            f"/fixtures/{fixture_id}",
            json={
                "expected_version": 1,
                "notes": "Updated fixture",
            },
        )

    assert response.status_code == 404

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_update_version_conflict(client, session):
    fixture_id = uuid4()

    with patch(
        "app.api.routes.fixtures.FixtureService"
    ) as service_class:
        service = service_class.return_value

        service.update_fixture = AsyncMock(
            side_effect=FixtureConflictError(
                "Fixture version mismatch."
            )
        )

        response = client.patch(
            f"/fixtures/{fixture_id}",
            json={
                "expected_version": 1,
                "notes": "Updated fixture",
            },
        )

    assert response.status_code == 409

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------
# TRANSACTION HANDLING
# ---------------------------------------

def test_generate_rolls_back_on_unexpected_error(client, session):
    tournament_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.generate_fixtures = AsyncMock(
            side_effect=RuntimeError(
                "Unexpected database error."
            )
        )

        with pytest.raises(
            RuntimeError,
            match="Unexpected database error",
        ):
            client.post(
                f"/fixtures/tournaments/{tournament_id}/generate",
                json=valid_generation_data(),
            )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_publish_rolls_back_on_unexpected_error(client, session):
    generation_run_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value

        service.publish_generation = AsyncMock(
            side_effect=RuntimeError(
                "Unexpected publication error."
            )
        )

        with pytest.raises(RuntimeError, match="Unexpected publication error"):
            client.post(
                f"/fixtures/generations/{generation_run_id}/publish",
                json={
                    "expected_fixture_count": 6,
                },
            )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_update_rolls_back_on_unexpected_error(client, session):
    fixture_id = uuid4()

    with patch("app.api.routes.fixtures.FixtureService") as service_class:
        service = service_class.return_value
        service.update_fixture = AsyncMock(
            side_effect=RuntimeError(
                "Unexpected update error."
            )
        )

        with pytest.raises(RuntimeError, match="Unexpected update error"):
            client.patch(
                f"/fixtures/{fixture_id}",
                json={
                    "expected_version": 1,
                    "notes": "Updated fixture",
                },
            )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
