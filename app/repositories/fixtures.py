"""Database access for the fixture workspace."""
from datetime import timedelta
from sqlalchemy import or_, select

from app.models import Match, MatchPlayer, Team, Tournament, TournamentTeam, TournamentVenue, Venue
from app.models.entities.fixtures import (
    Fixture, FixtureBracketDependency, FixtureChangeAudit, FixtureGenerationRun, FixtureRound, SchedulingConstraint, VenueAvailability,
)


class FixtureRepository:
    def __init__(self, session):
        self.session = session

    async def scheduling_lock(self):
        # Shared venues require serialization across tournament boundaries.
        from sqlalchemy import text
        await self.session.execute(text("SELECT pg_advisory_xact_lock(12012026)"))

    async def tournament(self, tournament_id, lock=False):
        query = select(Tournament).where(Tournament.id == tournament_id)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def teams(self, tournament_id):
        return list((await self.session.scalars(select(TournamentTeam).join(Team, Team.id == TournamentTeam.team_id)
            .where(TournamentTeam.tournament_id == tournament_id, TournamentTeam.registration_status == "approved",
                   TournamentTeam.is_reserve.is_(False), Team.status == "active", Team.archived_at.is_(None))
            .order_by(TournamentTeam.seed.asc().nulls_last(), TournamentTeam.team_id))).all())

    async def venues(self, tournament_id):
        return list((await self.session.scalars(select(Venue).join(TournamentVenue, TournamentVenue.venue_id == Venue.id)
            .where(TournamentVenue.tournament_id == tournament_id, Venue.status == "active", Venue.archived_at.is_(None)))).all())

    async def runs(self, tournament_id):
        return list((await self.session.scalars(select(FixtureGenerationRun)
            .where(FixtureGenerationRun.tournament_id == tournament_id)
            .order_by(FixtureGenerationRun.created_at.desc(), FixtureGenerationRun.id))).all())

    async def run(self, run_id, lock=False):
        query = select(FixtureGenerationRun).where(FixtureGenerationRun.id == run_id)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def fixtures(self, run_id, lock=False):
        query = select(Fixture).where(Fixture.generation_run_id == run_id).order_by(Fixture.fixture_number)
        return list((await self.session.scalars(query.with_for_update() if lock else query)).all())

    async def rounds(self, run_id):
        return list((await self.session.scalars(select(FixtureRound).where(FixtureRound.generation_run_id == run_id))).all())

    async def dependencies(self, run_id):
        return list((await self.session.scalars(select(FixtureBracketDependency)
            .join(Fixture, Fixture.id == FixtureBracketDependency.fixture_id)
            .where(Fixture.generation_run_id == run_id))).all())

    async def availability(self, venue_ids):
        # Shared-venue blackouts apply across competitions.
        return list((await self.session.scalars(select(VenueAvailability)
            .where(VenueAvailability.venue_id.in_(venue_ids)))).all()) if venue_ids else []

    async def constraints(self, tournament_id):
        return list((await self.session.scalars(select(SchedulingConstraint).where(
            SchedulingConstraint.tournament_id == tournament_id, SchedulingConstraint.is_active.is_(True)))).all())

    async def external(self, config, exclude_run=None):
        from app.domain.fixture_planning import scheduled
        fixtures = list((await self.session.scalars(select(Fixture).where(
            Fixture.scheduled_at.is_not(None), Fixture.ends_at.is_not(None), Fixture.venue_id.is_not(None),
            Fixture.status.notin_(["cancelled", "postponed"]),
            or_(Fixture.is_locked.is_(True), Fixture.status.in_(["published", "completed"])),
            *([Fixture.generation_run_id != exclude_run] if exclude_run else [])))).all())
        linked = set((await self.session.scalars(select(Fixture.match_id).where(Fixture.match_id.is_not(None)))).all())
        matches = list((await self.session.scalars(select(Match).where(Match.scheduled_at.is_not(None),
            Match.venue_id.is_not(None), Match.status != "abandoned"))).all())
        rows = [{"fixture_number": -index - 1, "round_number": 1, "home_team_id": str(row.home_team_id) if row.home_team_id else f"pending:{row.id}:home",
                 "away_team_id": str(row.away_team_id) if row.away_team_id else f"pending:{row.id}:away",
                 "venue_id": str(row.venue_id), "scheduled_at": row.scheduled_at, "ends_at": row.ends_at}
                for index, row in enumerate(fixtures)]
        for match in matches:
            if match.id not in linked:
                rows.append({"fixture_number": -len(rows) - 1, "round_number": 1,
                             "home_team_id": str(match.team_a_id), "away_team_id": str(match.team_b_id),
                             "venue_id": str(match.venue_id), "scheduled_at": match.scheduled_at,
                             "ends_at": match.scheduled_at + timedelta(minutes=config.duration_minutes)})
        return [scheduled(row) for row in rows]

    async def match_started(self, match):
        if match.status != "draft" or match.rules_locked_at or match.toss_winner_id:
            return True
        return await self.session.scalar(select(MatchPlayer.id).where(MatchPlayer.match_id == match.id).limit(1)) is not None

    async def audit(self, fixture_id):
        return list((await self.session.scalars(select(FixtureChangeAudit).where(FixtureChangeAudit.fixture_id == fixture_id)
            .order_by(FixtureChangeAudit.created_at.desc()).limit(100))).all())
