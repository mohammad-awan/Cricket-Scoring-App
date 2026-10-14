"""Domain-organized SQLAlchemy entity package.

Importing this package registers every mapped class with SQLAlchemy's shared
Base metadata.

Application code should normally import models from app.models, which remains
the stable public import boundary.
"""

from app.models.entities.audit import AuditLog
from app.models.entities.innings import Innings
from app.models.entities.matches import Match, MatchPlayer
from app.models.entities.players import Player
from app.models.entities.retirements import BatterRetirement
from app.models.entities.scoring import Delivery, DeliveryCorrection
from app.models.entities.teams import Team, TeamPlayer
from app.models.entities.tournaments import (
    Tournament,
    TournamentRuleSet,
    TournamentTeam,
    TournamentGroup,
    TournamentRoster,
    TournamentVenue,
    TournamentAsset,
    TournamentAuditEvent,
    TournamentPointDeduction,
    TournamentSeries,
)
from app.models.entities.venues import Venue


__all__ = [
    "AuditLog",
    "BatterRetirement",
    "Delivery",
    "DeliveryCorrection",
    "Innings",
    "Match",
    "MatchPlayer",
    "Player",
    "Team",
    "TeamPlayer",
    "Tournament",
    "TournamentAsset",
    "TournamentAuditEvent",
    "TournamentGroup",
    "TournamentPointDeduction",
    "TournamentRoster",
    "TournamentRuleSet",
    "TournamentSeries",
    "TournamentTeam",
    "TournamentVenue",
    "Venue",
]