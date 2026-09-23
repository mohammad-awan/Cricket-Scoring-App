from sqlalchemy.orm import configure_mappers
import app.models
from app.db.base import Base



def test_all_stage2_entities_are_registered() -> None:
    expected_tables = {
            "teams",
            "players",
            "team_players",
            "venues",
            "tournaments",
            "matches",
            "match_players",
            "innings",
            "deliveries",
            "delivery_corrections",
            "audit_logs",
        }

    assert expected_tables == set(Base.metadata.tables)



def test_relationships_require_explicit_loading() -> None:
    # Every relationship must be eager-loaded deliberately by a
    # repository query; implicit loading cascaded into dozens of
    # round trips per request.
    configure_mappers()

    for mapper in Base.registry.mappers:
        for relationship in mapper.relationships:
            assert relationship.lazy == "raise_on_sql", relationship


def test_constraints_and_indexes_are_named() -> None:
    teams = Base.metadata.tables["teams"]
    team_players = Base.metadata.tables["team_players"]
    matches = Base.metadata.tables["matches"]

    assert "uq_teams_code" in {
        constraint.name
        for constraint in teams.constraints
    }

    assert "uq_team_players_team_player" in {
        constraint.name
        for constraint in team_players.constraints
    }

    assert "ck_matches_matches_teams_must_differ" in {
        constraint.name
        for constraint in matches.constraints
    }