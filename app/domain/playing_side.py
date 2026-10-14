"""Playing-side sizes.

A match has a full side size (players_per_side) and may let a team start
with fewer players (minimum_players_to_start), as in gully, indoor or
short-handed club cricket. Once an innings starts, its batting side size is
fixed and decides when the side is all out.
"""

from __future__ import annotations
from typing import Any


def minimum_players(match: Any) -> int:
    """Fewest players a team may field; defaults to a full side."""

    return getattr(match, "minimum_players_to_start", None) or match.players_per_side


def side_size_allowed(match: Any, count: int) -> bool:
    return minimum_players(match) <= count <= match.players_per_side


def side_size_text(match: Any) -> str:
    minimum = minimum_players(match)

    if minimum == match.players_per_side:
        return f"exactly {match.players_per_side}"

    return f"between {minimum} and {match.players_per_side}"


def batting_side_size(match: Any, innings: Any) -> int:
    """Players available to bat in an innings (recorded at creation)."""

    return getattr(innings, "batting_side_size", None) or match.players_per_side
