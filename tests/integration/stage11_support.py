"""Shared fixtures for Stage 11 live-database tournament tests."""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from uuid import UUID, uuid4
import pytest
from sqlalchemy import delete, or_, select
from app.db.session import AsyncSessionFactory
from app.domain.tournament_rules import TournamentRules
from app.models import (
    AuditLog,
    Innings,
    Match,
    MatchPlayer,
    Player,
    Team,
    TeamPlayer,
    Tournament,
    TournamentAuditEvent,
    TournamentGroup,
    TournamentRoster,
    TournamentRuleSet,
    TournamentStatus,
    TournamentTeam,
    TournamentVenue,
    Venue,
)
from app.schemas.tournaments import (
    CompetitionConfigUpdate,
    RosterAdd,
    RuleVersionCreate,
    TournamentCreate,
    TournamentTeamRegister,
)
from app.services import tournaments as svc


live_db = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_TESTS") != "1",
    reason="Set RUN_LIVE_DB_TESTS=1 to run Stage 11 PostgreSQL tests",
)


def small_rules(**overrides) -> TournamentRules:
    """A fast two-a-side format so tests need few players."""

    values = {
        "format_code": "custom",
        "overs_per_innings": 2,
        "players_per_side": 2,
        "minimum_players_to_start": 2,
        "minimum_roster_size": 2,
        "maximum_roster_size": 3,
    }
    values.update(overrides)
    return TournamentRules(**values)


async def call(function, *args, **kwargs):
    """Run a service in its own session, like a separate request."""

    async with AsyncSessionFactory() as session:
        return await function(session, *args, **kwargs)


@dataclass
class World:
    suffix: str
    tournament_id: UUID
    venue_id: UUID
    team_ids: list[UUID]
    players: dict[UUID, list[UUID]]
    extra_tournament_ids: list[UUID] = field(default_factory=list)


async def build_world(
    *,
    teams: int = 2,
    players_per_team: int = 3,
    rules: TournamentRules | None = None,
    config: dict | None = None,
) -> World:
    suffix = uuid4().hex[:10]

    async with AsyncSessionFactory() as session:
        async with session.begin():
            venue = Venue(name=f"S11 Ground {suffix}", city="Lahore")
            session.add(venue)

            team_rows = [
                Team(
                    name=f"S11 Team {index} {suffix}",
                    short_name=f"T{index}{suffix[:4]}",
                    code=f"S11{index}{suffix[:6]}",
                )
                for index in range(teams)
            ]
            session.add_all(team_rows)
            await session.flush()

            players: dict[UUID, list[UUID]] = {}
            for index, team in enumerate(team_rows):
                rows = [
                    Player(full_name=f"S11 P{index}-{number} {suffix}")
                    for number in range(players_per_team)
                ]
                session.add_all(rows)
                await session.flush()
                session.add_all(
                    TeamPlayer(team_id=team.id, player_id=row.id) for row in rows
                )
                players[team.id] = [row.id for row in rows]

            venue_id = venue.id
            team_ids = [team.id for team in team_rows]

    tournament = await call(
        svc.create_tournament,
        TournamentCreate(name=f"S11 Cup {suffix}", season="2026"),
    )

    world = World(
        suffix=suffix,
        tournament_id=tournament.id,
        venue_id=venue_id,
        team_ids=team_ids,
        players=players,
    )

    if config:
        await call(
            svc.configure_tournament,
            world.tournament_id,
            CompetitionConfigUpdate(**config),
        )

    if rules is not None:
        await call(
            svc.create_tournament_rules,
            world.tournament_id,
            RuleVersionCreate(rules=rules),
        )

    return world


async def transition(world: World, target: TournamentStatus, reason=None):
    return await call(
        svc.change_tournament_status,
        world.tournament_id,
        target,
        reason,
    )


async def invite(world: World, team_id: UUID):
    return await call(
        svc.invite_tournament_team,
        world.tournament_id,
        TournamentTeamRegister(team_id=team_id),
    )


async def add_roster(world: World, membership_id: UUID, player_id: UUID):
    return await call(
        svc.add_tournament_roster_player,
        world.tournament_id,
        membership_id,
        RosterAdd(player_id=player_id),
    )


async def scheduled_world(*, teams: int = 2, roster_size: int = 2) -> tuple[World, dict]:
    """Tournament moved to SCHEDULED with every team invited and rostered.

    Returns the world and {team_id: membership_id}.
    """

    world = await build_world(teams=teams, rules=small_rules())
    await call(svc.assign_tournament_venue, world.tournament_id, world.venue_id)
    await transition(world, TournamentStatus.REGISTRATION_OPEN)

    memberships = {}
    for team_id in world.team_ids:
        membership = await invite(world, team_id)
        memberships[team_id] = membership.id
        for player_id in world.players[team_id][:roster_size]:
            await add_roster(world, membership.id, player_id)

    await transition(world, TournamentStatus.REGISTRATION_CLOSED)
    await transition(world, TournamentStatus.SCHEDULED)
    return world, memberships


async def cleanup(world: World) -> None:
    tournament_ids = [world.tournament_id, *world.extra_tournament_ids]

    async with AsyncSessionFactory() as session:
        async with session.begin():
            match_ids = list(
                (
                    await session.scalars(
                        select(Match.id).where(
                            or_(
                                Match.tournament_id.in_(tournament_ids),
                                Match.team_a_id.in_(world.team_ids),
                            )
                        )
                    )
                ).all()
            )
            membership_ids = select(TournamentTeam.id).where(
                TournamentTeam.tournament_id.in_(tournament_ids)
            )

            if match_ids:
                await session.execute(delete(Innings).where(Innings.match_id.in_(match_ids)))
                await session.execute(
                    delete(MatchPlayer).where(MatchPlayer.match_id.in_(match_ids))
                )
                await session.execute(delete(Match).where(Match.id.in_(match_ids)))

            await session.execute(
                delete(TournamentAuditEvent).where(
                    TournamentAuditEvent.tournament_id.in_(tournament_ids)
                )
            )
            await session.execute(
                delete(TournamentRoster).where(
                    TournamentRoster.tournament_team_id.in_(membership_ids)
                )
            )
            await session.execute(
                delete(TournamentTeam).where(
                    TournamentTeam.tournament_id.in_(tournament_ids)
                )
            )
            for model in (TournamentGroup, TournamentVenue, TournamentRuleSet):
                await session.execute(
                    delete(model).where(model.tournament_id.in_(tournament_ids))
                )
            await session.execute(
                delete(AuditLog).where(
                    AuditLog.entity_id.in_([*tournament_ids, *match_ids])
                )
            )
            await session.execute(delete(Tournament).where(Tournament.id.in_(tournament_ids)))
            await session.execute(
                delete(TeamPlayer).where(TeamPlayer.team_id.in_(world.team_ids))
            )
            player_ids = [item for ids in world.players.values() for item in ids]
            await session.execute(delete(Player).where(Player.id.in_(player_ids)))
            await session.execute(delete(Team).where(Team.id.in_(world.team_ids)))
            await session.execute(delete(Venue).where(Venue.id == world.venue_id))
