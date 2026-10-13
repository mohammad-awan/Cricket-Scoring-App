import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionFactory
from app.models import TournamentStatus
from app.schemas.tournaments import RuleVersionCreate, TournamentCreate
from app.services import tournaments as svc
from tests.integration.stage11_support import (
    build_world,
    call,
    cleanup,
    invite,
    live_db,
    scheduled_world,
    small_rules,
    transition,
)


pytestmark = [pytest.mark.integration, live_db]


async def _rules(world, rules):
    return await call(
        svc.create_tournament_rules,
        world.tournament_id,
        RuleVersionCreate(rules=rules),
    )


@pytest.mark.asyncio
async def test_rule_versions_are_append_only() -> None:
    world = await build_world()
    try:
        first = await _rules(world, small_rules())
        same = await _rules(world, small_rules())
        second = await _rules(world, small_rules(overs_per_innings=3))

        assert first.version == 1
        assert same.id == first.id
        assert second.version == 2

        current = await call(svc.get_current_tournament_rules, world.tournament_id)
        older = await call(svc.get_tournament_rule_version, world.tournament_id, 1)
        assert current.id == second.id
        assert older.rules["overs_per_innings"] == 2

        async with AsyncSessionFactory() as session:
            with pytest.raises(DBAPIError, match="immutable"):
                async with session.begin():
                    await session.execute(
                        text(
                            "UPDATE tournament_rule_sets SET created_by = 'x' "
                            "WHERE id = :id"
                        ),
                        {"id": first.id},
                    )
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_publication_requires_supported_rules() -> None:
    world = await build_world()
    try:
        with pytest.raises(ValidationError):
            await call(svc.set_tournament_publication, world.tournament_id, True)

        await _rules(world, small_rules(dls_enabled=True))
        with pytest.raises(ValidationError, match="DLS"):
            await call(svc.set_tournament_publication, world.tournament_id, True)

        await _rules(world, small_rules())
        published = await call(svc.set_tournament_publication, world.tournament_id, True)
        assert published.is_published is True

        unpublished = await call(svc.set_tournament_publication, world.tournament_id, False)
        assert unpublished.is_published is False
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_group_assignment_respects_group_size() -> None:
    world = await build_world(
        teams=3,
        rules=small_rules(structure="groups_knockout", teams_per_group=2),
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        group = await call(svc.create_tournament_group, world.tournament_id, "Group A")
        duplicate = await call(svc.create_tournament_group, world.tournament_id, "Group A")
        assert duplicate.id == group.id

        memberships = [await invite(world, team_id) for team_id in world.team_ids]

        for membership in memberships[:2]:
            assigned = await call(
                svc.assign_tournament_group,
                world.tournament_id,
                membership.id,
                group.id,
            )
            assert assigned.group_id == group.id

        with pytest.raises(ConflictError, match="already has"):
            await call(
                svc.assign_tournament_group,
                world.tournament_id,
                memberships[2].id,
                group.id,
            )

        with pytest.raises(ConflictError):
            await call(svc.delete_tournament_group, world.tournament_id, group.id)
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_lifecycle_guards_and_rule_lock_when_live() -> None:
    world, _ = await scheduled_world()
    try:
        tournament = await call(svc.get_tournament, world.tournament_id)
        assert tournament.status == TournamentStatus.SCHEDULED
        assert tournament.roster_lock_at is not None

        # Revisions are still allowed while scheduled...
        await _rules(world, small_rules(overs_per_innings=3))

        with pytest.raises(ValidationError):
            await transition(world, TournamentStatus.SUSPENDED)

        await transition(world, TournamentStatus.LIVE)

        # ...but locked once the tournament is live.
        with pytest.raises(ConflictError, match="locked"):
            await _rules(world, small_rules(overs_per_innings=4))

        with pytest.raises(ConflictError):
            await call(svc.archive_tournament, world.tournament_id)

        await transition(world, TournamentStatus.COMPLETED)
        archived = await call(svc.archive_tournament, world.tournament_id)
        assert archived.status == TournamentStatus.ARCHIVED
        assert archived.archived_at is not None
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_draft_cannot_skip_to_live_and_legacy_archive_still_works() -> None:
    world = await build_world(rules=small_rules())
    try:
        with pytest.raises(ConflictError):
            await transition(world, TournamentStatus.LIVE)

        # Governed draft must go through the lifecycle.
        with pytest.raises(ConflictError):
            await call(svc.archive_tournament, world.tournament_id)

        legacy = await call(
            svc.create_tournament,
            TournamentCreate(name=f"S11 Legacy {world.suffix}"),
        )
        world.extra_tournament_ids.append(legacy.id)

        archived = await call(svc.archive_tournament, legacy.id)
        assert archived.status == TournamentStatus.ARCHIVED
    finally:
        await cleanup(world)
