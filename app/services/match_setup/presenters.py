from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError
from app.models import Match
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import (
    InningsSetupRead,
    MatchSetupRead,
    TeamSummary,
    TournamentSummary,
    VenueSummary,
)
from app.services.match_setup.rules import evaluate_readiness


def match_setup_read(
    match: Match,
) -> MatchSetupRead:

    return MatchSetupRead(
        id=match.id,

        title=match.title,

        match_number=(
            match.match_number
        ),

        team_a=(
            TeamSummary.model_validate(
                match.team_a
            )
        ),

        team_b=(
            TeamSummary.model_validate(
                match.team_b
            )
        ),

        tournament=(
            TournamentSummary.model_validate(
                match.tournament
            )
            if match.tournament
            else None
        ),

        venue=(
            VenueSummary.model_validate(
                match.venue
            )
            if match.venue
            else None
        ),

        match_type=(
            match.match_type
        ),

        players_per_side=(
            match.players_per_side
        ),

        total_overs=(
            match.total_overs
        ),

        balls_per_over=(
            match.balls_per_over
        ),

        innings_per_team=(
            match.innings_per_team
        ),

        scheduled_at=(
            match.scheduled_at
        ),

        status=(
            match.status
        ),

        created_at=(
            match.created_at
        ),

        updated_at=(
            match.updated_at
        ),

        toss_winner=(
            TeamSummary.model_validate(
                match.toss_winner
            )
            if match.toss_winner
            else None
        ),

        toss_decision=(
            match.toss_decision
        ),

        players=(
            match.players
        ),

        innings=[
            InningsSetupRead.model_validate(
                item
            )
            for item in match.innings
        ],

        readiness=(
            evaluate_readiness(
                match
            )
        ),
    )


async def reload_match(
    session: AsyncSession,
    repository: MatchSetupRepository,
    match_id: UUID,
) -> Match:
    """
    Reload authoritative match state
    after setup mutations.

    This avoids returning stale ORM
    relationship collections from the
    current SQLAlchemy identity map.
    """

    await session.flush()

    session.expire_all()

    match = await repository.get_match(
        match_id
    )

    if match is None:
        raise NotFoundError(
            "Match not found"
        )

    return match
