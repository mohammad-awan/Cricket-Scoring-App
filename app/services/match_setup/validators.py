from __future__ import annotations
from uuid import UUID
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Team, TeamStatus, TournamentStatus, VenueStatus
from app.repositories.match_setup import MatchSetupRepository


async def require_active_team(
    repository: MatchSetupRepository,
    team_id: UUID,
    label: str,
) -> Team:

    team = await repository.get_team(
        team_id
    )

    if team is None:
        raise NotFoundError(
            f"{label} not found"
        )

    if (
        team.status
        != TeamStatus.ACTIVE
        or team.archived_at is not None
    ):
        raise ConflictError(
            f"{label} must be active"
        )

    return team


async def validate_match_references(
    repository: MatchSetupRepository,
    *,
    team_a_id: UUID,
    team_b_id: UUID,
    venue_id: UUID | None,
    tournament_id: UUID | None,
) -> tuple[Team, Team]:

    if team_a_id == team_b_id:
        raise ValidationError(
            "Team A and Team B "
            "must be different"
        )

    team_a = await require_active_team(
        repository,
        team_a_id,
        "Team A",
    )

    team_b = await require_active_team(
        repository,
        team_b_id,
        "Team B",
    )

    if venue_id is not None:

        venue = await repository.get_venue(
            venue_id
        )

        if venue is None:
            raise NotFoundError(
                "Venue not found"
            )

        if (
            venue.status
            != VenueStatus.ACTIVE
            or venue.archived_at
            is not None
        ):
            raise ConflictError(
                "Venue must be active"
            )

    if tournament_id is not None:

        tournament = (
            await repository
            .get_tournament(
                tournament_id
            )
        )

        if tournament is None:
            raise NotFoundError(
                "Tournament not found"
            )

        if (
            tournament.status
            == TournamentStatus.ARCHIVED
            or tournament.archived_at
            is not None
        ):
            raise ConflictError(
                "Archived tournament "
                "cannot be used for a match"
            )

    return (
        team_a,
        team_b,
    )
