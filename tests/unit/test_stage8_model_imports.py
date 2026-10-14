from sqlalchemy.orm import configure_mappers
from app.db.base import Base
from app.models import (
    AuditLog,
    Delivery,
    DeliveryCorrection,
    Innings,
    Match,
    MatchPlayer,
    Player,
    Team,
    TeamPlayer,
    Tournament,
    Venue,
)


def test_stage8_public_model_imports_and_mapper_configuration() -> None:
    exported_models = (
        AuditLog,
        Delivery,
        DeliveryCorrection,
        Innings,
        Match,
        MatchPlayer,
        Player,
        Team,
        TeamPlayer,
        Tournament,
        Venue,
    )

    assert all(model.__table__ is not None for model in exported_models)

    configure_mappers()

    assert set(Base.metadata.tables) == {
        "audit_logs",
        "batter_retirements",
        "deliveries",
        "delivery_corrections",
        "innings",
        "match_players",
        "matches",
        "players",
        "team_players",
        "teams",
        "tournaments",
        "tournament_assets",
        "tournament_audit_events",
        "tournament_groups",
        "tournament_point_deductions",
        "tournament_rosters",
        "tournament_rule_sets",
        "tournament_series",
        "tournament_teams",
        "tournament_venues",
        "venues",
    }


def test_stage8_models_live_in_their_domain_modules() -> None:
    expected_modules = {
        Team: "teams",
        TeamPlayer: "teams",
        Player: "players",
        Venue: "venues",
        Tournament: "tournaments",
        Match: "matches",
        MatchPlayer: "matches",
        Innings: "innings",
        Delivery: "scoring",
        DeliveryCorrection: "scoring",
        AuditLog: "audit",
    }

    for model, module in expected_modules.items():
        assert model.__module__ == f"app.models.entities.{module}"
