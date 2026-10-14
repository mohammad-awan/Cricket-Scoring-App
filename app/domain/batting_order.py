from __future__ import annotations
from collections.abc import Iterable
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models import MatchPlayer
from app.schemas.scoring import BatterSelectionMode


def validate_batting_order(
    selections: Iterable[MatchPlayer],
    *,
    players_per_side: int,
    minimum_players: int | None = None,
) -> list[UUID]:
    """
    Return player IDs in batting order.

    A ready team fields between minimum_players
    (default: a full side) and players_per_side
    players, with batting positions 1..N for the
    N players it actually fields.
    """
    players = list(selections)
    minimum = minimum_players or players_per_side

    if not minimum <= len(players) <= players_per_side:
        expected = (
            f"exactly {players_per_side}"
            if minimum == players_per_side
            else f"between {minimum} and {players_per_side}"
        )
        raise ValidationError(
            f"Expected {expected} players in the playing team"
        )

    players_ids = [p.player_id for p in players]

    if len(set(players_ids)) != len(players_ids):
        raise ValidationError(
            "A player cannot appear twice in the playing team"
        )

    positions = [p.batting_order for p in players]

    if any(position is None for position in positions):
        raise ValidationError(
            "Every selected player must be have"
            "a batting order before match readiness"
        )

    expected = set(range(1, len(players) + 1))

    if set(positions) != expected:
        raise ValidationError(
            "Batting order must contain every "
            f"position from 1 to {len(players)} exactly once"
        )

    return [
        player.player_id
        for player in sorted(players, key=lambda player: player.batting_order)
    ]


def select_next_batter(
        ordered_player_ids: list[UUID],
        *,
        striker_id: UUID,
        non_striker_id: UUID,
        dismissed_player_ids: set[UUID],
        dismissed_player_id: UUID,
        selection_mode: BatterSelectionMode = "automatic",
        manual_player_id: UUID | None = None,
        final_wicket: bool = False,
        resumable_player_ids: set[UUID] = frozenset(),
) -> UUID | None:
    """
    Resolve the incoming batter.

    Automatic mode picks the first eligible batter
    in batting order who has not yet batted. Manual
    mode lets the scorer promote any eligible batter,
    including a retired-hurt batter resuming their
    innings; skipped batters remain available for
    later wickets.

    Returns None after the final wicket.
    """
    unavailable = set(dismissed_player_ids) | {striker_id, non_striker_id, dismissed_player_id}

    eligible_players = [
        player_id
        for player_id in ordered_player_ids
        if player_id not in unavailable
    ]

    if final_wicket:
        if manual_player_id is not None:
            raise ValidationError("No incoming batter is permitted after the final wicket.")
        return None

    if not eligible_players:
        raise ValidationError("No eligible incoming batter found.")

    if selection_mode == "automatic":
        if manual_player_id is not None:
            raise ValidationError("Manual batter ID cannot be supplied in automatic mode.")

        # A retired-hurt batter resumes only by
        # the scorer's explicit choice.
        fresh_players = [
            player_id
            for player_id in eligible_players
            if player_id not in resumable_player_ids
        ]

        if not fresh_players:
            raise ValidationError(
                "Only retired-hurt batters remain. "
                "Select the batter who will resume."
            )
        return fresh_players[0]

    if selection_mode == "manual":
        if manual_player_id is None:
            raise ValidationError("Please select the incoming batter for manual mode.")
        if manual_player_id not in eligible_players:
            raise ValidationError("Selected incoming batter is not eligible to bat.")
        return manual_player_id

    raise ValidationError("Invalid incoming batter selection mode.")