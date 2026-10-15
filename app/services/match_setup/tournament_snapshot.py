"""Stage 11 bridge between match setup and tournament competition rules.

A tournament with at least one rule version is *governed*: its fixtures
must use approved teams, permitted venues and the configured match format,
and every playing XI must come from the tournament roster. When a governed
match becomes Ready, the current rule version is snapshotted onto the match
so later rule revisions cannot change a Ready/Live match.

Tournaments without rule versions are legacy records and keep the Stage 10
behaviour unchanged.
"""

from __future__ import annotations
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, ValidationError
from app.domain.tournament_rules import (
    TournamentRules,
    match_config_from_rules,
    match_config_mismatches,
    validate_for_activation,
)
from app.models import Match, Tournament, TournamentRuleSet, TournamentStatus
from app.repositories.tournaments import TournamentRepository
from app.domain.playing_side import minimum_players
from app.services.tournament_eligibility import (
    overseas_limit_errors,
    players_eligibility_errors,
)


FIXTURE_TOURNAMENT_STATUSES = frozenset(
    {
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
    }
)

READY_TOURNAMENT_STATUSES = frozenset(
    {
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
    }
)


def lineup_roster_errors(
    *,
    team_label: str,
    selected_ids: Iterable[UUID],
    roster_ids: set[UUID],
    captain_count: int,
) -> list[str]:
    errors = []
    outside = sorted(set(selected_ids) - roster_ids, key=str)

    if outside:
        errors.append(
            f"{team_label} playing team includes players who are not "
            "available on the tournament roster: "
            + ", ".join(str(item) for item in outside)
        )

    if captain_count > 1:
        errors.append(f"{team_label} playing team has more than one captain")

    return errors


async def governing_rules(
    repository: TournamentRepository,
    tournament_id: UUID | None,
) -> TournamentRuleSet | None:
    if tournament_id is None:
        return None

    return await repository.latest_rules(tournament_id)


async def team_and_venue_errors(
    repository: TournamentRepository,
    tournament_id: UUID,
    *,
    team_a_id: UUID,
    team_b_id: UUID,
    venue_id: UUID | None,
    require_venue: bool = False,
) -> list[str]:
    """Validate participating teams and tournament venues.

    Draft fixtures may omit their venue.
    Ready fixtures must use a configured permitted venue
    when the tournament has a venue list.
    """

    errors: list[str] = []

    if team_a_id == team_b_id:
        errors.append("A tournament match requires two different teams")

    approved_teams = await repository.approved_team_ids(tournament_id)

    if team_a_id not in approved_teams:
        errors.append("Team A is not approved for this tournament")

    if team_b_id not in approved_teams:
        errors.append("Team B is not approved for this tournament")

    assigned_venues = await repository.list_venues(tournament_id)

    permitted_venue_ids = {
        item.venue_id
        for item in assigned_venues
    }

    if venue_id is None:
        if require_venue and permitted_venue_ids:
            errors.append(
                "A permitted tournament venue must be "
                "selected before the match becomes Ready"
            )

    elif venue_id not in permitted_venue_ids:
        errors.append(
            "The selected venue is not assigned "
            "to this tournament"
        )

    return errors



async def apply_tournament_fixture_rules(
    session: AsyncSession,
    *,
    tournament_id: UUID | None,
    team_a_id: UUID,
    team_b_id: UUID,
    venue_id: UUID | None,
    config: dict[str, Any],
    explicit_fields: set[str],
) -> dict[str, Any]:
    """Validate a fixture against its tournament and fill format defaults.

    Fields the caller did not set explicitly take the tournament rule
    values; explicitly supplied values must agree with the rules.
    Returns the (possibly filled) config unchanged for legacy tournaments.
    """

    repository = TournamentRepository(session)
    ruleset = await governing_rules(repository, tournament_id)

    if ruleset is None:
        return config

    tournament = await session.get(Tournament, tournament_id)
    if tournament is not None and tournament.status not in FIXTURE_TOURNAMENT_STATUSES:
        raise ConflictError(
            "Fixtures cannot be created or changed while the "
            f"tournament is {tournament.status.value}"
        )

    rules = TournamentRules.model_validate(ruleset.rules)
    errors = await team_and_venue_errors(
        repository,
        ruleset.tournament_id,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        venue_id=venue_id,
    )

    result = dict(config)
    for field, expected in match_config_from_rules(rules).items():
        if field in explicit_fields and config.get(field) != expected:
            errors.append(f"{field} must be {expected} for this tournament")
        else:
            result[field] = expected

    if errors:
        raise ValidationError("; ".join(errors))

    return result


async def validate_tournament_lineup(
    session: AsyncSession,
    match: Match,
    team_id: UUID,
    player_ids: set[UUID],
) -> None:
    repository = TournamentRepository(session)
    ruleset = await governing_rules(repository, match.tournament_id)

    if ruleset is None:
        return

    rules = TournamentRules.model_validate(ruleset.rules)
    tournament = await session.get(Tournament, match.tournament_id)
    roster_ids = await repository.available_roster_player_ids(
        match.tournament_id,
        team_id,
    )
    errors = lineup_roster_errors(
        team_label="Selected",
        selected_ids=player_ids,
        roster_ids=roster_ids,
        captain_count=0,
    )
    errors.extend(
        await overseas_limit_errors(
            repository,
            rules,
            team_label="Selected",
            player_ids=player_ids,
        )
    )
    if tournament is not None:
        errors.extend(
            await players_eligibility_errors(repository, tournament, rules, player_ids)
        )
    if errors:
        raise ValidationError("; ".join(errors))


async def lock_match_tournament_rules(session: AsyncSession, match: Match) -> None:
    """Validate a governed match and snapshot its rules before Ready.

    Must run inside the mark-ready transaction, with the match row locked.
    """

    if match.tournament_id is None:
        return

    if match.rules_locked_at is not None:
        raise ConflictError("Tournament match rules already locked")

    repository = TournamentRepository(session)
    ruleset = await governing_rules(repository, match.tournament_id)

    if ruleset is None:
        return

    tournament = await session.get(Tournament, match.tournament_id)
    if tournament is None or tournament.status not in READY_TOURNAMENT_STATUSES:
        raise ConflictError(
            "Tournament must be scheduled or live before "
            "its matches can be ready"
        )

    rules = TournamentRules.model_validate(ruleset.rules)
    validate_for_activation(rules)

    errors = match_config_mismatches(
        rules,
        {
            "players_per_side": match.players_per_side,
            "minimum_players_to_start": minimum_players(match),
            "total_overs": match.total_overs,
            "balls_per_over": match.balls_per_over,
            "innings_per_team": match.innings_per_team,
        },
    )
    errors.extend(
        await team_and_venue_errors(
            repository,
            match.tournament_id,
            team_a_id=match.team_a_id,
            team_b_id=match.team_b_id,
            venue_id=match.venue_id,
            require_venue=True
        )
    )

    for label, team_id in (("Team A", match.team_a_id), ("Team B", match.team_b_id)):
        selections = [item for item in match.players if item.team_id == team_id]
        errors.extend(
            lineup_roster_errors(
                team_label=label,
                selected_ids=[item.player_id for item in selections],
                roster_ids=await repository.available_roster_player_ids(
                    match.tournament_id,
                    team_id,
                ),
                captain_count=sum(1 for item in selections if item.is_captain),
            )
        )
        selected_ids = [item.player_id for item in selections]
        errors.extend(
            await overseas_limit_errors(
                repository,
                rules,
                team_label=label,
                player_ids=selected_ids,
            )
        )
        errors.extend(await players_eligibility_errors(repository, tournament, rules, selected_ids))

    if errors:
        raise ValidationError("Match does not satisfy tournament rules: " + "; ".join(errors))

    match.tournament_ruleset_id = ruleset.id
    match.effective_rules = ruleset.rules
    match.effective_rules_checksum = ruleset.checksum
    match.rules_locked_at = datetime.now(UTC)
