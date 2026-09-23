from __future__ import annotations
from datetime import date
from uuid import UUID
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload, selectinload
from app.models import (
    Innings,
    Match,
    MatchPlayer,
    Player,
    PlayerStatus,
    Team,
    TeamPlayer,
    Tournament,
    Venue,
)
from app.models.enums import MatchStatus



class MatchSetupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    def _detail_options(self):

        # Every query is a network round trip to Supabase, so
        # many-to-one references are JOINed into their parent
        # query and each collection costs exactly one query:
        # match + players + innings = 3 queries in total.
        players = selectinload(Match.players)
        innings = selectinload(Match.innings)

        return (
            joinedload(Match.team_a),
            joinedload(Match.team_b),
            joinedload(Match.tournament),
            joinedload(Match.venue),
            joinedload(Match.toss_winner),
            players.joinedload(MatchPlayer.team),
            players.joinedload(MatchPlayer.player),
            innings.joinedload(Innings.batting_team),
            innings.joinedload(Innings.bowling_team),
            innings.joinedload(Innings.striker),
            innings.joinedload(Innings.non_striker),
            innings.joinedload(Innings.current_bowler),
        )


    async def get_match(self, match_id: UUID, *, for_update: bool = False) -> Match | None:
        statement = (select(Match).where(Match.id == match_id)
            .options(*self._detail_options())
            .execution_options(populate_existing=True)
        )
        if for_update:
            # Lock only the match row; PostgreSQL rejects FOR UPDATE
            # on the nullable side of the outer joins above.
            statement = statement.with_for_update(of=Match)

        return await self.session.scalar(statement)


    async def list_matches(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        match_status: MatchStatus | None,
    ) -> list[Match]:

        team_a = aliased(Team)
        team_b = aliased(Team)

        statement = (
            select(Match)
            .join(
                team_a,
                Match.team_a_id
                == team_a.id,
            )
            .join(
                team_b,
                Match.team_b_id
                == team_b.id,
            )
            .options(
                contains_eager(Match.team_a.of_type(team_a)),
                contains_eager(Match.team_b.of_type(team_b)),
                joinedload(Match.tournament),
                joinedload(Match.venue),
            )
        )

        conditions = []

        if search:
            pattern = (f"%{search.strip().lower()}%")
            conditions.append(
                or_(
                    func.lower(
                        func.coalesce(
                            Match.title,
                            "",
                        )
                    ).like(pattern),

                    func.lower(
                        team_a.name
                    ).like(pattern),

                    func.lower(
                        team_b.name
                    ).like(pattern),

                    func.lower(
                        team_a.code
                    ).like(pattern),

                    func.lower(
                        team_b.code
                    ).like(pattern),
                )
            )

        if match_status is not None:
            conditions.append(Match.status == match_status)

        statement = (
            statement
            .where(*conditions)
            .order_by(Match.scheduled_at.desc().nullslast(), Match.created_at.desc())
            .offset(
                (page - 1)
                * page_size
            )
            .limit(page_size)
        )

        result = await self.session.scalars(statement)
        return list(result.unique().all())


    async def count_matches(
        self,
        *,
        search: str | None,
        match_status: MatchStatus | None,
    ) -> int:

        team_a = aliased(Team)
        team_b = aliased(Team)
        statement = (
            select(func.count(Match.id))
            .join(team_a, Match.team_a_id == team_a.id)
            .join(
                team_b,
                Match.team_b_id
                == team_b.id,
            )
        )
        conditions = []

        if search:
            pattern = (f"%{search.strip().lower()}%")
            conditions.append(
                or_(
                    func.lower(
                        func.coalesce(
                            Match.title,
                            "",
                        )
                    ).like(pattern),

                    func.lower(team_a.name).like(pattern),
                    func.lower(team_b.name).like(pattern),
                    func.lower(team_a.code).like(pattern),
                    func.lower(team_b.code).like(pattern),
                )
            )

        if match_status is not None:
            conditions.append(Match.status == match_status)

        statement = statement.where(*conditions)

        return int(await self.session.scalar(statement) or 0)


    async def get_team(self, team_id: UUID) -> Team | None:
        return await self.session.get(Team, team_id)


    async def get_player(self, player_id: UUID) -> Player | None:
        return await self.session.get(Player, player_id)


    async def get_team_player_membership(
        self,
        team_id: UUID,
        player_id: UUID,
    ) -> TeamPlayer | None:

        statement = (
            select(TeamPlayer)
            .where(
                TeamPlayer.team_id
                == team_id,

                TeamPlayer.player_id
                == player_id,
            )
            .options(
                joinedload(
                    TeamPlayer.player
                )
            )
        )

        return await self.session.scalar(statement)


    async def get_venue(self, venue_id: UUID) -> Venue | None:
        return await self.session.get(Venue, venue_id)


    async def get_tournament(
        self,
        tournament_id: UUID,
    ) -> Tournament | None:

        return await self.session.get(Tournament, tournament_id)


    async def get_active_squad(self, team_id: UUID) -> list[TeamPlayer]:
        today = date.today()
        statement = (
            select(TeamPlayer)

            .join(
                Player,
                TeamPlayer.player_id
                == Player.id,
            )
            .where(
                TeamPlayer.team_id == team_id,
                TeamPlayer.is_active.is_(
                    True
                ),
                or_(
                    TeamPlayer.left_on.is_(
                        None
                    ),

                    TeamPlayer.left_on
                    >= today,
                ),

                Player.status
                == PlayerStatus.ACTIVE,
            )

            .options(
                contains_eager(
                    TeamPlayer.player
                )
            )

            .order_by(
                TeamPlayer.squad_number
                .asc()
                .nullslast(),

                Player.full_name.asc(),
            )
        )

        result = await self.session.scalars(statement)
        return list(result.all())


    async def get_active_squad_memberships(
        self,
        team_id: UUID,
        player_ids: set[UUID],
    ) -> dict[UUID, TeamPlayer]:

        if not player_ids:
            return {}

        today = date.today()
        statement = (
            select(TeamPlayer)
            .join(
                Player,
                TeamPlayer.player_id
                == Player.id,
            )
            .where(
                TeamPlayer.team_id
                == team_id,

                TeamPlayer.player_id.in_(
                    player_ids
                ),

                TeamPlayer.is_active.is_(
                    True
                ),

                or_(
                    TeamPlayer.left_on.is_(
                        None
                    ),

                    TeamPlayer.left_on
                    >= today,
                ),

                Player.status
                == PlayerStatus.ACTIVE,
            )

            .options(
                contains_eager(
                    TeamPlayer.player
                )
            )
        )

        result = await self.session.scalars(statement)
        return {
            item.player_id: item
            for item in result.all()
        }


    async def replace_playing_xi(
        self,
        *,
        match_id: UUID,
        team_id: UUID,
        selections: list[MatchPlayer],
    ) -> None:

        await self.session.execute(
            delete(
                MatchPlayer
            ).where(
                MatchPlayer.match_id
                == match_id,

                MatchPlayer.team_id
                == team_id,
            )
        )

        self.session.add_all(selections)
        await self.session.flush()


    async def get_first_innings(self, match_id: UUID) -> Innings | None:
        statement = (
            select(Innings)
            .where(
                Innings.match_id
                == match_id,

                Innings.innings_number
                == 1,
            )
            .options(
                joinedload(Innings.batting_team),
                joinedload(Innings.bowling_team),
                joinedload(Innings.striker),
                joinedload(Innings.non_striker),
                joinedload(Innings.current_bowler),
                selectinload(Innings.deliveries),
            )
        )

        return await self.session.scalar(statement)