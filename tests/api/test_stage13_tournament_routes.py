"""Stage 13 tournament operation, statistics, award and report routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes import tournament_awards, tournament_operations, tournament_reports, tournament_statistics
from app.core.exceptions import ConflictError, register_exception_handlers
from app.db.session import get_db_session


TOURNAMENT = uuid4()


@pytest.fixture
def session():
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=TOURNAMENT))
    return db


@pytest.fixture
def client(session):
    app = FastAPI()
    for module in (tournament_operations, tournament_statistics, tournament_awards, tournament_reports):
        app.include_router(module.router)
    app.include_router(tournament_statistics.series_router)
    register_exception_handlers(app)

    async def override():
        yield session

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as test_client:
        yield test_client


def test_standings_route_returns_service_result(client):
    payload = {"tables": [], "pending_fixtures": []}
    with patch.object(tournament_operations, "calculate_tournament_standings", AsyncMock(return_value=payload)):
        response = client.get(f"/tournaments/{TOURNAMENT}/standings")
    assert response.status_code == 200 and response.json() == payload


def test_qualification_passes_best_ranked_parameters(client):
    service = AsyncMock(return_value={"groups": []})
    with patch.object(tournament_operations, "tournament_qualification", service):
        response = client.get(f"/tournaments/{TOURNAMENT}/qualification?top_k=2&best_rank=3&best_count=2")
    assert response.status_code == 200
    assert service.await_args.args[2] == 2
    assert service.await_args.kwargs == {"best_rank": 3, "best_count": 2}


def test_disposition_validates_outcome_and_reason(client):
    fixture_id = uuid4()
    response = client.post(f"/tournaments/{TOURNAMENT}/fixtures/{fixture_id}/disposition", json={"outcome": "replay", "reason": "x" * 12})
    assert response.status_code == 422
    response = client.post(f"/tournaments/{TOURNAMENT}/fixtures/{fixture_id}/disposition", json={"outcome": "walkover", "reason": "short"})
    assert response.status_code == 422


def test_disposition_publishes_committed_event(client):
    fixture_id, winner = uuid4(), uuid4()
    service = AsyncMock(return_value={"fixture_id": str(fixture_id), "outcome": "walkover"})
    event = AsyncMock()
    with patch.object(tournament_operations, "record_fixture_disposition", service), \
         patch.object(tournament_operations, "publish_tournament_event", event):
        response = client.post(
            f"/tournaments/{TOURNAMENT}/fixtures/{fixture_id}/disposition",
            json={"outcome": "walkover", "winner_team_id": str(winner), "reason": "Opponent did not arrive"},
        )
    assert response.status_code == 200
    assert service.await_args.kwargs["winner_team_id"] == winner
    event.assert_awaited_once()
    assert event.await_args.args[1] == "result_committed"


def test_service_conflicts_map_to_409_without_events(client):
    event = AsyncMock()
    with patch.object(tournament_operations, "finalize_tournament", AsyncMock(side_effect=ConflictError("Cannot finalize: Fixture 3 is postponed"))), \
         patch.object(tournament_operations, "publish_tournament_event", event):
        response = client.post(f"/tournaments/{TOURNAMENT}/finalize")
    assert response.status_code == 409
    assert "postponed" in response.text
    event.assert_not_awaited()


def test_finalize_returns_frozen_closeout_and_notifies(client):
    closeout = SimpleNamespace(tournament_id=TOURNAMENT, champion_team_id=uuid4(), revision=1, is_frozen=True,
                               finalized_at="2026-11-25T10:00:00+00:00", snapshot={"schema_version": 2})
    event = AsyncMock()
    with patch.object(tournament_operations, "finalize_tournament", AsyncMock(return_value=closeout)), \
         patch.object(tournament_operations, "publish_tournament_event", event):
        response = client.post(f"/tournaments/{TOURNAMENT}/finalize")
    assert response.status_code == 200 and response.json()["is_frozen"] is True
    assert event.await_args.args[1] == "tournament_finalized"


def test_reopen_requires_reason_and_returns_policy(client):
    assert client.post(f"/tournaments/{TOURNAMENT}/reopen", json={"reason": "no"}).status_code == 422
    closeout = SimpleNamespace(tournament_id=TOURNAMENT, revision=1, is_frozen=False, reopened_at=None, reopen_reason="Scorer error in final")
    with patch.object(tournament_operations, "reopen_tournament", AsyncMock(return_value=closeout)), \
         patch.object(tournament_operations, "publish_tournament_event", AsyncMock()):
        response = client.post(f"/tournaments/{TOURNAMENT}/reopen", json={"reason": "Scorer error in final"})
    assert response.status_code == 200 and response.json()["reopening_policy"]


def test_leaderboards_apply_qualification_filters(client):
    data = {"batting": [{"player_id": "1", "qualifies": True}, {"player_id": "2", "qualifies": False}],
            "bowling": [], "fielding": [], "dismissal_summary": {}}
    with patch.object(tournament_statistics, "tournament_statistics_data", AsyncMock(return_value={})), \
         patch.object(tournament_statistics, "compute_player_statistics", MagicMock(return_value=data)) as compute:
        response = client.get(f"/tournaments/{TOURNAMENT}/leaderboards?min_innings=2&qualified_only=true")
    assert response.status_code == 200
    assert [row["player_id"] for row in response.json()["batting"]] == ["1"]
    assert compute.call_args.kwargs["min_innings"] == 2


def test_standings_csv_export(client):
    rows = [{"group_name": "League", "rank": 1, "team_name": "Alpha", "points": 4, "net_run_rate": 1.25, "team_id": "t1"}]
    with patch.object(tournament_reports, "standings_rows", AsyncMock(return_value=rows)):
        response = client.get(f"/tournaments/{TOURNAMENT}/export/standings.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("group_name,rank,team_name")
    assert lines[1].startswith("League,1,Alpha")


def test_award_confirmation_requires_single_recipient(client):
    response = client.post(f"/tournaments/{TOURNAMENT}/awards/player_of_tournament/confirm",
                           json={"reason": "Outstanding all-round season", "player_id": str(uuid4()), "team_id": str(uuid4())})
    assert response.status_code == 422


def test_award_confirmation_passes_basis(client):
    award = SimpleNamespace(id=uuid4(), tournament_id=TOURNAMENT, award_code="player_of_tournament", player_id=uuid4(), team_id=None,
                            status="confirmed", selection_method="manual", evidence={"basis": "organizer_selection", "override": True},
                            reason="Committee preferred all-round impact", confirmed_by=None, confirmed_at=None)
    service = AsyncMock(return_value=award)
    with patch.object(tournament_awards, "confirm_award", service), \
         patch.object(tournament_awards, "publish_tournament_event", AsyncMock()):
        response = client.post(f"/tournaments/{TOURNAMENT}/awards/player_of_tournament/confirm",
                               json={"player_id": str(award.player_id), "reason": award.reason, "basis": "organizer_selection"})
    assert response.status_code == 200
    assert response.json()["override"] is True
    assert service.await_args.kwargs["basis"] == "organizer_selection"


def test_series_routes_404_for_unknown_series(client, session):
    session.get = AsyncMock(return_value=None)
    assert client.get(f"/tournament-series/{uuid4()}/leaderboards").status_code == 404
    assert client.get(f"/tournament-series/{uuid4()}/history").status_code == 404
