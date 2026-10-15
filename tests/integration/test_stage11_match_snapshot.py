import pytest
from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionFactory
from app.models import Match, MatchStatus, Team, TossDecision, Venue
from app.schemas.match_setup import (
    MatchCreate,
    OpeningInningsSetup,
    PlayingTeamPlayer,
    PlayingTeamSetup,
    TossSetup,
)
from app.schemas.tournaments import (
    RulePropagationRequest,
    RuleVersionCreate,
)
from app.services import tournaments as svc
from app.services.match_setup import (
    create_match,
    mark_match_ready,
    set_playing_team,
    set_toss,
    setup_opening_innings,
)
from tests.integration.stage11_support import (
    call,
    cleanup,
    live_db,
    scheduled_world,
    small_rules,
)


pytestmark = [pytest.mark.integration, live_db]


def _lineup(player_ids) -> PlayingTeamSetup:
    return PlayingTeamSetup(
        players=[
            PlayingTeamPlayer(
                player_id=player_id,
                batting_order=index,
                is_captain=index == 1,
                is_wicket_keeper=index == 2,
            )
            for index, player_id in enumerate(player_ids, start=1)
        ]
    )


@pytest.mark.asyncio
async def test_ready_match_snapshots_rules_and_ignores_later_revisions() -> None:
    world, _ = await scheduled_world(teams=2, roster_size=2)
    team_a, team_b = world.team_ids
    try:
        # Explicit match settings must agree with
        # the configured tournament rules.
        with pytest.raises(ValidationError, match="total_overs"):
            await call(
                create_match,
                MatchCreate(
                    team_a_id=team_a,
                    team_b_id=team_b,
                    tournament_id=world.tournament_id,
                    total_overs=20,
                ),
            )

        # Omitted match settings are inherited
        # from the tournament rule configuration.
        setup = await call(
            create_match,
            MatchCreate(
                team_a_id=team_a,
                team_b_id=team_b,
                tournament_id=world.tournament_id,
                venue_id=world.venue_id,
                scheduled_at="2026-11-20T10:00:00+05:00",
            ),
        )

        match_id = setup.id
        async with AsyncSessionFactory() as session:
            match = await session.get(Match, match_id)
            assert match.players_per_side == 2
            assert match.total_overs == 2

        # A player outside the tournament roster
        # must not be included in the playing side.
        with pytest.raises(ValidationError, match="roster"):
            await call(
                set_playing_team,
                match_id,
                team_a,
                _lineup(world.players[team_a][1:3]),
            )

        await call(
            set_playing_team,
            match_id,
            team_a,
            _lineup(world.players[team_a][:2]),
        )
        await call(
            set_playing_team,
            match_id,
            team_b,
            _lineup(world.players[team_b][:2]),
        )
        await call(
            set_toss,
            match_id,
            TossSetup(
                winner_team_id=team_a,
                decision=TossDecision.BAT,
            ),
        )
        await call(
            setup_opening_innings,
            match_id,
            OpeningInningsSetup(
                striker_id=world.players[team_a][0],
                non_striker_id=world.players[team_a][1],
                opening_bowler_id=world.players[team_b][0],
            ),
        )
        # Ready matches must lock their effective rules.
        await call(mark_match_ready, match_id)
        current = await call(svc.get_current_tournament_rules, world.tournament_id)

        async with AsyncSessionFactory() as session:
            match = await session.get(Match, match_id)
            assert match.status == MatchStatus.READY
            assert match.rules_locked_at is not None
            assert match.tournament_ruleset_id == current.id
            assert match.effective_rules_checksum == current.checksum

        # Create a new tournament rule version.
        revised = await call(
            svc.create_tournament_rules,
            world.tournament_id,
            RuleVersionCreate(
                rules=small_rules(
                    overs_per_innings=5,
                )
            ),
        )

        assert revised.version == current.version + 1
        # Propagation must not modify Ready matches.
        result = await call(
            svc.propagate_tournament_rules,
            world.tournament_id,
            RulePropagationRequest(
                apply_to_unstarted=True,
                expected_previous_version=revised.version,
            ),
        )

        assert match_id not in result["updated_match_ids"]
        # Historical rules remain unchanged.
        async with AsyncSessionFactory() as session:
            match = await session.get(Match, match_id)
            assert match.tournament_ruleset_id == current.id
            assert match.total_overs == 2
            assert match.effective_rules["overs_per_innings"] == 2

    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_fixture_requires_approved_teams_and_permitted_venue() -> None:
    world, _ = await scheduled_world(teams=2, roster_size=2)

    team_a, team_b = world.team_ids
    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                outsider = Team(
                    name=f"S11 Outsider {world.suffix}",
                    short_name=f"O{world.suffix[:4]}",
                    code=f"S11O{world.suffix[:6]}",
                )
                other_venue = Venue(
                    name=f"S11 Other {world.suffix}",
                    city="Karachi",
                )
                session.add_all([
                    outsider,
                    other_venue,
                ])
                await session.flush()
                outsider_id = outsider.id
                other_venue_id = other_venue.id

        # Register the outsider for test cleanup.
        world.team_ids.append(outsider_id)

        # Unapproved tournament teams must be rejected.
        with pytest.raises(ValidationError, match=r"not approved for this tournament"):
            await call(
                create_match,
                MatchCreate(
                    team_a_id=team_a,
                    team_b_id=outsider_id,
                    tournament_id=world.tournament_id,
                ),
            )

        try:
            # Only assigned tournament venues are permitted.
            with pytest.raises(ValidationError, match=r"not assigned to this tournament"):
                await call(
                    create_match,
                    MatchCreate(
                        team_a_id=team_a,
                        team_b_id=team_b,
                        tournament_id=world.tournament_id,
                        venue_id=other_venue_id,
                    ),
                )

        finally:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    venue = await session.get(
                        Venue,
                        other_venue_id,
                    )

                    if venue is not None:
                        await session.delete(venue)

    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_propagation_detects_stale_version() -> None:
    world, _ = await scheduled_world()

    try:
        current = await call(svc.get_current_tournament_rules, world.tournament_id)

        # Stale rule propagation requests must be rejected.
        with pytest.raises(ConflictError, match="current version"):
            await call(
                svc.propagate_tournament_rules,
                world.tournament_id,
                RulePropagationRequest(
                    apply_to_unstarted=False,
                    expected_previous_version=current.version + 5,
                ),
            )

    finally:
        await cleanup(world)
