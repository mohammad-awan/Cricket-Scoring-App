from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.master_data import (
    TeamCreate,
    TeamUpdate,
    TournamentCreate,
)


def test_team_create_strips_input() -> None:
    payload = TeamCreate(
        name="  Pakistan  ",
        short_name=" PAK ",
        code=" pak ",
    )

    assert payload.name == "Pakistan"
    assert payload.short_name == "PAK"
    assert payload.code == "pak"


def test_empty_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TeamUpdate()


def test_tournament_dates_are_validated() -> None:
    with pytest.raises(ValidationError):
        TournamentCreate(
            name="Tournament",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 9),
        )