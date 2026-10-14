"""Stage 11 player eligibility checks backed by the database.

Shared by roster management, tournament readiness and match setup so the
same age / sex / nationality rules apply everywhere.
"""

from __future__ import annotations
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID
from app.domain.tournament_eligibility import (
    eligibility_reference_date,
    overseas_count,
    player_eligibility_errors,
)
from app.domain.tournament_rules import TournamentRules
from app.models import Player, Tournament
from app.repositories.tournaments import TournamentRepository


def player_errors(
    player: Player,
    tournament: Tournament,
    rules: TournamentRules,
    *,
    label: str | None = None,
) -> list[str]:
    return player_eligibility_errors(
        label=label or player.full_name,
        date_of_birth=player.date_of_birth,
        sex=player.sex.value if player.sex else None,
        nationality=player.nationality,
        policy=rules.eligibility,
        reference_date=eligibility_reference_date(
            rules.eligibility,
            tournament.start_date,
            datetime.now(UTC).date(),
        ),
        overseas_limit_active=rules.overseas_player_limit is not None,
    )


async def players_eligibility_errors(
    repository: TournamentRepository,
    tournament: Tournament,
    rules: TournamentRules,
    player_ids: Iterable[UUID],
) -> list[str]:
    players = await repository.players_by_ids(set(player_ids))
    errors: list[str] = []

    for player in players.values():
        errors.extend(player_errors(player, tournament, rules))

    return errors


async def overseas_limit_errors(
    repository: TournamentRepository,
    rules: TournamentRules,
    *,
    team_label: str,
    player_ids: Iterable[UUID],
) -> list[str]:
    limit = rules.overseas_player_limit
    if limit is None:
        return []

    players = await repository.players_by_ids(set(player_ids))
    count = overseas_count(
        (player.nationality for player in players.values()),
        rules.eligibility.home_nationality,
    )

    if count > limit:
        return [
            f"{team_label} playing team has {count} overseas players; "
            f"the limit is {limit}"
        ]

    return []
