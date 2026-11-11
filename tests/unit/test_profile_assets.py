from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import Player
from app.schemas.venues import VenueCreate, VenueUpdate
from app.services import player_profile
from tests.unit.test_stage11_migration_sql import render


@pytest.mark.parametrize("schema", [VenueCreate, VenueUpdate])
@pytest.mark.parametrize("coordinates", [
    {"latitude": 31.5},
    {"latitude": None},
    {"latitude": 31.5, "longitude": None},
    {"latitude": 91, "longitude": 74.3},
    {"latitude": 31.5, "longitude": -181},
    {"latitude": float("nan"), "longitude": 74.3},
])
def test_invalid_coordinate_pairs_are_rejected(schema, coordinates):
    with pytest.raises(ValidationError):
        schema(name="Stadium", city="Lahore", **coordinates)


@pytest.mark.parametrize("coordinates", [
    {"latitude": 0, "longitude": 0},
    {"latitude": -90, "longitude": 180},
    {"latitude": None, "longitude": None},
])
def test_coordinate_updates_accept_zero_boundaries_and_clearing(coordinates):
    assert VenueUpdate(**coordinates).model_dump(exclude_unset=True) == coordinates


async def test_player_profile_includes_saved_photo_and_source(monkeypatch):
    player = Player(
        id=uuid4(), full_name="Babar Azam", status="active",
        photo_url="https://example.com/babar.jpg",
        photo_source_url="https://example.com/players/babar",
    )
    monkeypatch.setattr(player_profile, "require_player", AsyncMock(return_value=player))
    repository = SimpleNamespace(
        activity_rows=AsyncMock(return_value=[]),
        active_team_memberships=AsyncMock(return_value=[]),
        match_history_page=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(player_profile, "PlayerProfileRepository", lambda session: repository)

    result = await player_profile.get_player_profile(None, player.id)
    identity = result.model_dump(mode="json")["player"]

    assert identity["photo_url"] == player.photo_url
    assert identity["photo_source_url"] == player.photo_source_url


def test_profile_asset_migration_renders_upgrade_and_downgrade():
    upgrade = render("upgrade", "845e2be3dfb1:20261112_0015")
    downgrade = render("downgrade", "20261112_0015:845e2be3dfb1")

    for table, column in [
        ("players", "photo_url"), ("players", "photo_source_url"),
        ("teams", "logo_url"), ("teams", "logo_source_url"),
        ("venues", "image_url"), ("venues", "latitude"), ("venues", "longitude"),
    ]:
        assert f"ALTER TABLE {table} ADD COLUMN {column}" in upgrade
        assert f"ALTER TABLE {table} DROP COLUMN {column}" in downgrade
    assert "latitude IS NULL AND longitude IS NULL" in upgrade
