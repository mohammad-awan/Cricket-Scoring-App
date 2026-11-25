
from __future__ import annotations
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Match, MatchStatus
from app.models.entities.fixtures import Fixture, FixtureBracketDependency, FixtureChangeAudit


class BracketAdvancementError(Exception):
    pass


class BracketAdvancementConflict(BracketAdvancementError):
    pass


async def advance_bracket_dependency(
    session: AsyncSession,
    dependency_id: UUID,
    *,
    reason: str = "Official completed match result",
) -> dict:
    """
    Advance one knockout dependency.

    The caller owns the database transaction.

    This operation never changes a linked Match.
    A downstream fixture with an existing Match
    must be handled by the match setup workflow.
    """

    dependency = await session.scalar(
        select(FixtureBracketDependency).where(
            FixtureBracketDependency.id == dependency_id
        )
    )

    if dependency is None:
        raise BracketAdvancementError("Bracket dependency not found")

    fixture_ids = sorted(
        {
            dependency.source_fixture_id,
            dependency.fixture_id,
        },
        key=str,
    )

    fixtures = (
        await session.scalars(
            select(Fixture)
            .where(Fixture.id.in_(fixture_ids))
            .order_by(Fixture.id)
            .with_for_update()
        )
    ).all()

    fixture_map = {
        fixture.id: fixture for fixture in fixtures
    }

    source = fixture_map.get(dependency.source_fixture_id)
    target = fixture_map.get(dependency.fixture_id)

    if source is None or target is None:
        raise BracketAdvancementConflict("Source or target fixture is missing")

    if source.tournament_id != target.tournament_id:
        raise BracketAdvancementConflict(
            "Bracket fixtures belong to "
            "different tournaments"
        )

    if source.match_id is None:
        raise BracketAdvancementConflict("Source fixture has no official match")

    source_match = await session.scalar(
        select(Match)
        .where(Match.id == source.match_id)
        .with_for_update()
    )

    if source_match is None:
        raise BracketAdvancementConflict("Source match not found")

    if (
        source_match.tournament_id
        != source.tournament_id
    ):
        raise BracketAdvancementConflict("Source match tournament mismatch")

    if source_match.status != MatchStatus.COMPLETED:
        raise BracketAdvancementConflict("Source match is not completed")

    winner = source_match.winner_team_id

    if winner is None:
        raise BracketAdvancementConflict("Source match has no resolved winner")

    if winner not in {
        source_match.team_a_id,
        source_match.team_b_id,
    }:
        raise BracketAdvancementConflict("Invalid official match winner")

    if dependency.advancement == "winner":
        advancing_team_id = winner

    elif dependency.advancement == "loser":
        advancing_team_id = (
            source_match.team_b_id
            if winner == source_match.team_a_id
            else source_match.team_a_id
        )

    else:
        raise BracketAdvancementConflict("Unsupported advancement rule")

    if dependency.target_side == "home":
        current_team_id = target.home_team_id
        opposite_team_id = target.away_team_id
        field_name = "home_team_id"

    elif dependency.target_side == "away":
        current_team_id = target.away_team_id
        opposite_team_id = target.home_team_id
        field_name = "away_team_id"

    else:
        raise BracketAdvancementConflict("Invalid target bracket side")

    if opposite_team_id == advancing_team_id:
        raise BracketAdvancementConflict("A team cannot play itself")

    if current_team_id == advancing_team_id:
        return {
            "dependency_id": dependency.id,
            "target_fixture_id": target.id,
            "advancing_team_id": advancing_team_id,
            "changed": False,
            "status": "already_assigned",
        }

    if target.status in {"completed", "cancelled"}:
        raise BracketAdvancementConflict("Target fixture cannot be modified")

    if target.is_locked:
        raise BracketAdvancementConflict("Target fixture is locked")

    if target.match_id is not None:
        # Never change the fixture independently
        # from its linked official Match.
        raise BracketAdvancementConflict(
            "Target fixture already has a linked "
            "Match. Review and update through "
            "the official match setup workflow."
        )

    if current_team_id is not None:
        raise BracketAdvancementConflict(
            "Target bracket slot already contains "
            "a different team. Manual review required."
        )

    setattr(target, field_name, advancing_team_id)

    target.version += 1

    session.add(
        FixtureChangeAudit(
            fixture_id=target.id,
            action="bracket_advancement",
            old_values={
                field_name: None,
            },
            new_values={
                field_name: str(advancing_team_id),
                "source_fixture_id": str(source.id),
                "source_match_id": str(source_match.id),
                "dependency_id": str(dependency.id),
                "version": target.version,
            },
            reason=reason,
        )
    )

    await session.flush()

    return {
        "dependency_id": dependency.id,
        "source_fixture_id": source.id,
        "target_fixture_id": target.id,
        "advancing_team_id": advancing_team_id,
        "target_side": dependency.target_side,
        "changed": True,
        "status": "assigned",
        "fixture_version": target.version,
    }
