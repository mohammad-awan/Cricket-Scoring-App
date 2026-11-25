
from __future__ import annotations
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Match, MatchStatus, Tournament
from app.models.entities.fixtures import Fixture, FixtureBracketDependency


async def review_bracket(session: AsyncSession, tournament_id: UUID) -> dict:
    tournament = await session.get(Tournament, tournament_id)

    if tournament is None:
        raise ValueError("Tournament not found")

    fixtures = (
        await session.scalars(
            select(Fixture).where(
                Fixture.tournament_id == tournament_id
            )
        )
    ).all()

    fixture_map = {fixture.id: fixture for fixture in fixtures}
    match_ids = [fixture.match_id for fixture in fixtures if fixture.match_id is not None]

    matches = (
        await session.scalars(
            select(Match).where(
                Match.id.in_(match_ids)
            )
        )
    ).all() if match_ids else []

    match_map = {match.id: match for match in matches}

    dependencies = (
        await session.scalars(
            select(FixtureBracketDependency)
            .join(
                Fixture,
                FixtureBracketDependency.fixture_id
                == Fixture.id,
            )
            .where(Fixture.tournament_id == tournament_id)
        )
    ).all()

    reviews = []

    for dependency in dependencies:
        source = fixture_map.get(dependency.source_fixture_id)
        target = fixture_map.get(dependency.fixture_id)

        result = {
            "dependency_id": dependency.id,
            "source_fixture_id":
                dependency.source_fixture_id,
            "target_fixture_id":
                dependency.fixture_id,
            "target_side": dependency.target_side,
            "advancement": dependency.advancement,
            "expected_team_id": None,
            "actual_team_id": None,
            "status": "awaiting_result",
        }

        if source is None or target is None:
            result["status"] = "invalid_dependency"
            reviews.append(result)
            continue

        source_match = match_map.get(source.match_id)

        if (
            source_match is None
            or source_match.status
            != MatchStatus.COMPLETED
        ):
            reviews.append(result)
            continue

        winner = source_match.winner_team_id

        if winner is None:
            result["status"] = "requires_adjudication"
            reviews.append(result)
            continue

        expected = (
            winner
            if dependency.advancement == "winner"
            else (
                source_match.team_b_id
                if winner == source_match.team_a_id
                else source_match.team_a_id
            )
        )

        actual = (
            target.home_team_id
            if dependency.target_side == "home"
            else target.away_team_id
        )

        result["expected_team_id"] = expected
        result["actual_team_id"] = actual

        if actual == expected:
            result["status"] = "consistent"
        elif actual is None:
            result["status"] = "slot_unassigned"
        else:
            result["status"] = "requires_review"

        target_match = match_map.get(target.match_id)

        if target_match is not None:
            match_team = (
                target_match.team_a_id
                if dependency.target_side == "home"
                else target_match.team_b_id
            )

            if match_team != expected:
                result["status"] = "requires_review"

            if target_match.status in {
                MatchStatus.LIVE,
                MatchStatus.INNINGS_BREAK,
                MatchStatus.COMPLETED,
            } and result["status"] != "consistent":
                result["status"] = "locked_conflict"

        reviews.append(result)

    return {
        "tournament_id": tournament_id,
        "dependencies": reviews,
        "unresolved_count": sum(
            item["status"] != "consistent"
            for item in reviews
        ),
        "automatic_mutation": False,
    }
