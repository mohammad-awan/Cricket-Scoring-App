import asyncio
import pytest
from app.core.exceptions import ConflictError, ValidationError
from app.models import TournamentStatus
from app.schemas.tournaments import CompetitionConfigUpdate, TournamentTeamRegister
from app.services import tournaments as svc
from tests.integration.stage11_support import (
    build_world,
    call,
    cleanup,
    live_db,
    small_rules,
    transition,
)


pytestmark = [pytest.mark.integration, live_db]


async def _register(world, team_id, **extra):
    return await call(
        svc.register_tournament_team,
        world.tournament_id,
        TournamentTeamRegister(team_id=team_id, **extra),
    )


@pytest.mark.asyncio
async def test_two_team_competition_registration_and_approval() -> None:
    world = await build_world(teams=2, rules=small_rules())
    try:
        with pytest.raises(ConflictError):
            await _register(world, world.team_ids[0])

        await transition(world, TournamentStatus.REGISTRATION_OPEN)

        first = await _register(world, world.team_ids[0])
        again = await _register(world, world.team_ids[0])
        second = await _register(world, world.team_ids[1])

        assert first.registration_status == "pending"
        assert again.id == first.id

        with pytest.raises(ValidationError):
            await call(
                svc.decide_tournament_registration,
                world.tournament_id,
                second.id,
                False,
            )

        for membership in (first, second):
            approved = await call(
                svc.decide_tournament_registration,
                world.tournament_id,
                membership.id,
                True,
            )
            assert approved.registration_status == "approved"

        preview = await call(svc.validate_tournament_readiness, world.tournament_id)
        assert preview["approved_teams"] == 2
        assert not any("Not enough approved" in item for item in preview["errors"])
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_capacity_overflows_to_reserve_then_rejects() -> None:
    world = await build_world(
        teams=4,
        rules=small_rules(),
        config={"maximum_teams": 2, "reserve_team_limit": 1},
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)

        main = [await _register(world, team_id) for team_id in world.team_ids[:2]]
        reserve = await _register(world, world.team_ids[2])

        assert [item.is_reserve for item in main] == [False, False]
        assert reserve.is_reserve is True

        with pytest.raises(ConflictError, match="full"):
            await _register(world, world.team_ids[3])

        with pytest.raises(ConflictError):
            await call(
                svc.configure_tournament,
                world.tournament_id,
                CompetitionConfigUpdate(reserve_team_limit=0),
            )
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_parallel_registrations_respect_capacity() -> None:
    world = await build_world(
        teams=6,
        rules=small_rules(),
        config={"maximum_teams": 3},
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)

        results = await asyncio.gather(
            *(_register(world, team_id) for team_id in world.team_ids),
            return_exceptions=True,
        )

        admitted = [item for item in results if not isinstance(item, Exception)]
        rejected = [item for item in results if isinstance(item, ConflictError)]

        assert len(admitted) == 3
        assert len(rejected) == 3
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_odd_team_count_and_large_capacity() -> None:
    world = await build_world(
        teams=5,
        rules=small_rules(),
        config={"minimum_teams": 3, "maximum_teams": 256},
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)

        for team_id in world.team_ids:
            await call(
                svc.invite_tournament_team,
                world.tournament_id,
                TournamentTeamRegister(team_id=team_id),
            )

        preview = await call(svc.validate_tournament_readiness, world.tournament_id)

        assert preview["approved_teams"] == 5
        assert not any("Not enough approved" in item for item in preview["errors"])
        # Rosters are still empty, so scheduling must stay blocked.
        assert any("roster" in item for item in preview["errors"])

        await transition(world, TournamentStatus.REGISTRATION_CLOSED)

        with pytest.raises(ValidationError):
            await transition(world, TournamentStatus.SCHEDULED)
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_invitational_rejection_and_withdrawal() -> None:
    world = await build_world(
        teams=3,
        rules=small_rules(),
        config={"registration_mode": "invitational"},
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)

        with pytest.raises(ConflictError, match="invitation"):
            await _register(world, world.team_ids[0])

        invited = await call(
            svc.invite_tournament_team,
            world.tournament_id,
            TournamentTeamRegister(team_id=world.team_ids[0]),
        )
        assert invited.registration_status == "approved"

        withdrawn = await call(
            svc.withdraw_tournament_team,
            world.tournament_id,
            invited.id,
            "Team cannot travel",
        )
        assert withdrawn.registration_status == "withdrawn"

        readmitted = await call(
            svc.invite_tournament_team,
            world.tournament_id,
            TournamentTeamRegister(team_id=world.team_ids[0]),
        )
        assert readmitted.id == invited.id
        assert readmitted.registration_status == "approved"
    finally:
        await cleanup(world)
