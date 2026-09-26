from __future__ import annotations
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.models import Delivery, Innings, Match, MatchPlayer, Player, DeliveryStatus


class ScoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    async def lock_current_innings(self, match_id: UUID) -> Innings | None:
        """
        Critical Stage 4 concurrency lock.

        Every scoring transaction locks
        the latest innings row before
        calculating sequence, score,
        strike state or the next innings.
        """

        statement = (
            select(Innings)
            .where(Innings.match_id == match_id)
            .order_by(Innings.innings_number.desc())
            .limit(1)
            .with_for_update(of=Innings)
        )

        return await self.session.scalar(statement)


    async def get_current_innings(self, match_id: UUID) -> Innings | None:
        statement = (
            select(Innings)
            .where(Innings.match_id == match_id)
            .options(
                joinedload(Innings.batting_team),
                joinedload(Innings.bowling_team),
            )
            .order_by(Innings.innings_number.desc())
            .limit(1)
        )

        return await self.session.scalar(statement)


    async def list_innings(self, match_id: UUID) -> list[Innings]:
        statement = (
            select(Innings)
            .where(Innings.match_id == match_id)
            .options(
                joinedload(Innings.batting_team),
                joinedload(Innings.bowling_team),
            )
            .order_by(Innings.innings_number.asc())
        )

        result = await self.session.scalars(statement)

        return list(result.all())


    async def delivery_totals(self, match_id: UUID) -> dict[UUID, tuple[int, int]]:
        """
        Runs and legal balls per innings,
        aggregated from recorded delivery
        history (never from cached totals).
        """

        statement = (
            select(
                Delivery.innings_id,
                func.coalesce(func.sum(Delivery.total_runs), 0),
                func.count(Delivery.id).filter(Delivery.is_legal_ball.is_(True)),
            )
            .where(
                Delivery.match_id == match_id,
                Delivery.status == DeliveryStatus.RECORDED,
            )
            .group_by(Delivery.innings_id)
        )

        result = await self.session.execute(statement)

        return {
            innings_id: (int(runs), int(legal_balls))
            for innings_id, runs, legal_balls in result.all()
        }


    async def get_match(self, match_id: UUID) -> Match | None:
        statement = (
            select(Match)
            .where(Match.id == match_id)
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()


    async def get_recorded_deliveries(self, innings_id: UUID) -> list[Delivery]:
        statement = (
            select(Delivery)
            .where(
                Delivery.innings_id
                == innings_id,

                Delivery.status
                == DeliveryStatus.RECORDED,
            )
            .options(
                joinedload(
                    Delivery.striker
                ),

                joinedload(
                    Delivery.non_striker
                ),

                joinedload(
                    Delivery.bowler
                ),
            )
            .order_by(
                Delivery
                .delivery_number
                .asc()
            )
        )

        result = await self.session.scalars(statement)
        return list(result.all())


    async def get_recorded_deliveries_plain(self, innings_id: UUID) -> list[Delivery]:
        statement = (
            select(Delivery)
            .where(
                Delivery.innings_id
                == innings_id,

                Delivery.status
                == DeliveryStatus.RECORDED,
            )
            .order_by(
                Delivery
                .delivery_number
                .asc()
            )
        )

        result = await self.session.scalars(statement)

        return list(result.all())


    async def next_delivery_number(self, innings_id: UUID) -> int:
        """
        Sequence never rewinds.

        Stage 5 will be allowed to VOID
        deliveries, but their sequence
        numbers remain permanent.
        """

        statement = (
            select(
                func.coalesce(
                    func.max(
                        Delivery.delivery_number
                    ),
                    0,
                )
                + 1
            )
            .where(
                Delivery.innings_id
                == innings_id
            )
        )

        value = await self.session.scalar(
            statement
        )

        return int(
            value or 1
        )


    async def get_player(self, player_id: UUID) -> Player | None:
        return await self.session.get(Player, player_id)


    async def is_playing_team_player(self, *, match_id: UUID, team_id: UUID, player_id: UUID) -> bool:
        statement = (
            select(
                MatchPlayer.id
            )
            .where(
                MatchPlayer.match_id
                == match_id,

                MatchPlayer.team_id
                == team_id,

                MatchPlayer.player_id
                == player_id,
            )
        )

        result = await self.session.scalar(statement)

        return result is not None

        