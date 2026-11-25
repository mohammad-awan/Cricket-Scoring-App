from __future__ import annotations
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    Match,
    MatchStatus,
    Tournament,
    TournamentStatus,
)
from app.models.entities.fixtures import (
    Fixture,
    FixtureBracketDependency,
)


async def guard_tournament_result_correction(
    session: AsyncSession,
    match_id: UUID,
) -> None:
    """
    Block corrections that would silently change
    official tournament outcomes.

    Must run inside the caller's correction
    transaction.
    """

    match = await session.get(
        Match,
        match_id,
    )

    if match is None:
        raise NotFoundError("Match not found")

    if match.tournament_id is None:
        return

    tournament = await session.get(
        Tournament,
        match.tournament_id,
    )

    if tournament is None:
        raise NotFoundError("Tournament not found")

    if tournament.status in {
        TournamentStatus.COMPLETED,
        TournamentStatus.ARCHIVED,
    }:
        raise ConflictError(
            "Reopen the tournament before "
            "correcting an official result"
        )

    if match.status != MatchStatus.COMPLETED:
        return

    source_fixture = aliased(Fixture)

    downstream = (
        await session.execute(
            select(Fixture.id, Fixture.match_id)
            .join(
                FixtureBracketDependency,
                FixtureBracketDependency.fixture_id
                == Fixture.id,
            )
            .join(
                source_fixture,
                FixtureBracketDependency.source_fixture_id
                == source_fixture.id,
            )
            .where(source_fixture.match_id == match_id)
        )
    ).all()

    downstream_match_ids = [
        target_match_id
        for _, target_match_id in downstream
        if target_match_id is not None
    ]

    if not downstream_match_ids:
        return

    protected = await session.scalar(
        select(Match.id)
        .where(
            Match.id.in_(downstream_match_ids),
            Match.status.in_([
                MatchStatus.LIVE,
                MatchStatus.INNINGS_BREAK,
                MatchStatus.COMPLETED,
            ]),
        )
        .limit(1)
    )

    if protected is not None:
        raise ConflictError(
            "A downstream bracket match has "
            "already started from this result"
        )
