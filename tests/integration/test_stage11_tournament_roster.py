import pytest
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.session import AsyncSessionFactory
from app.models import TeamPlayer, TournamentStatus
from app.services import tournaments as svc
from tests.integration.stage11_support import (
    add_roster,
    build_world,
    call,
    cleanup,
    invite,
    live_db,
    small_rules,
    transition,
)


pytestmark = [pytest.mark.integration, live_db]


@pytest.mark.asyncio
async def test_roster_size_duplicates_eligibility_and_locking() -> None:
    world = await build_world(teams=2, players_per_team=5, rules=small_rules())
    team_a, team_b = world.team_ids
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        membership_a = await invite(world, team_a)
        membership_b = await invite(world, team_b)
        squad_a = world.players[team_a]

        first = await add_roster(world, membership_a.id, squad_a[0])
        again = await add_roster(world, membership_a.id, squad_a[0])
        assert again.id == first.id

        # Not in team A's active squad.
        with pytest.raises(ValidationError, match="active squad"):
            await add_roster(world, membership_a.id, world.players[team_b][0])

        # A player in both squads may only be rostered once per tournament.
        async with AsyncSessionFactory() as session:
            async with session.begin():
                session.add(TeamPlayer(team_id=team_b, player_id=squad_a[0]))

        with pytest.raises(ConflictError, match="another team"):
            await add_roster(world, membership_b.id, squad_a[0])

        await add_roster(world, membership_a.id, squad_a[1])
        await add_roster(world, membership_a.id, squad_a[2])

        with pytest.raises(ConflictError, match="Maximum"):
            await add_roster(world, membership_a.id, squad_a[3])

        with pytest.raises(ValidationError):
            await call(
                svc.set_tournament_captain,
                world.tournament_id,
                membership_a.id,
                squad_a[4],
            )

        captain = await call(
            svc.set_tournament_captain,
            world.tournament_id,
            membership_a.id,
            squad_a[0],
        )
        assert captain.captain_player_id == squad_a[0]

        removed = await call(
            svc.remove_tournament_roster_player,
            world.tournament_id,
            membership_a.id,
            squad_a[2],
        )
        assert removed == {"removed": True}

        locked = await call(svc.lock_tournament_rosters, world.tournament_id, "Deadline")
        assert locked["locked_entries"] == 2

        with pytest.raises(ConflictError):
            await call(
                svc.remove_tournament_roster_player,
                world.tournament_id,
                membership_a.id,
                squad_a[1],
            )

        # Injuries can still be recorded after the lock.
        entry = await call(
            svc.set_roster_availability,
            world.tournament_id,
            membership_a.id,
            squad_a[1],
            False,
            "Hamstring",
        )
        assert entry.is_available is False

        with pytest.raises(NotFoundError):
            await call(
                svc.set_roster_availability,
                world.tournament_id,
                membership_a.id,
                squad_a[4],
                False,
            )
    finally:
        await cleanup(world)
