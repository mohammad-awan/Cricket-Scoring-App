from __future__ import annotations
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from app.models import (
    BatterRetirement,
    Delivery,
    Innings,
    Match,
    MatchPlayer,
    Player,
)
from app.models.enums import DeliveryStatus, RetirementType


class ScoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    async def lock_current_innings(self, match_id: UUID) -> Innings | None:
        """
        The same row lock used in
        Stage 4 now protects delivery,
        wicket and correction writes.
        """

        statement = (
            select(
                Innings
            )
            .where(
                Innings.match_id
                == match_id
            )
            .order_by(
                Innings
                .innings_number
                .desc()
            )
            .limit(1)
            .with_for_update(
                of=Innings
            )
        )

        return await self.session.scalar(statement)

    
    async def get_playing_xi(self, match_id: UUID, team_id: UUID) -> list[MatchPlayer]:
        """
        Read official match selections in
        ascending batting order.
        """
        statement = (
            select(MatchPlayer)
            .where(
                MatchPlayer.match_id == match_id,
                MatchPlayer.team_id == team_id,
            )
            .order_by(
                MatchPlayer.batting_order.asc(),
                MatchPlayer.player_id.asc(),
            )
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    
    async def get_delivery_by_event_id(self, match_id: UUID, client_event_id: UUID) -> Delivery | None:
        statement = (
            select(Delivery)
            .where(
                Delivery.match_id == match_id,
                Delivery.client_event_id == client_event_id,
            )
        )

        return await self.session.scalar(statement)



    async def get_current_innings(self, match_id: UUID) -> Innings | None:
        statement = (
            select(
                Innings
            )
            .where(
                Innings.match_id
                == match_id
            )
            .options(
                joinedload(
                    Innings.batting_team
                ),
                joinedload(
                    Innings.bowling_team
                ),
            )
            .order_by(
                Innings
                .innings_number
                .desc()
            )
            .limit(1)
        )

        return await self.session.scalar(
            statement
        )


    async def list_innings(self, match_id: UUID) -> list[Innings]:
        statement = (
            select(
                Innings
            )
            .where(
                Innings.match_id
                == match_id
            )
            .options(
                joinedload(
                    Innings.batting_team
                ),
                joinedload(
                    Innings.bowling_team
                ),
            )
            .order_by(
                Innings
                .innings_number
                .asc()
            )
        )

        result = await self.session.scalars(statement)

        return list(result.all())


    async def delivery_totals(
        self,
        match_id: UUID,
    ) -> dict[
        UUID,
        tuple[
            int,
            int,
            int,
        ],
    ]:
        """
        Returns:

        innings_id ->
            (
                runs,
                legal_balls,
                wickets
            )

        Only non-void deliveries count.
        """

        statement = (
            select(
                Delivery.innings_id,
                func.coalesce(
                    func.sum(
                        Delivery.total_runs
                    ),
                    0,
                ),
                func.count(
                    Delivery.id
                ).filter(
                    Delivery
                    .is_legal_ball
                    .is_(True)
                ),
                func.count(
                    Delivery.id
                ).filter(
                    Delivery
                    .dismissed_player_id
                    .is_not(None)
                ),
            )
            .where(
                Delivery.match_id
                == match_id,

                Delivery.status
                == DeliveryStatus.RECORDED,
            )
            .group_by(
                Delivery.innings_id
            )
        )

        result = await self.session.execute(statement)

        totals = {
            innings_id: (
                int(runs),
                int(legal_balls),
                int(wickets),
            )
            for (
                innings_id,
                runs,
                legal_balls,
                wickets,
            )
            in result.all()
        }

        # Retired out is a dismissal with no delivery.
        retired_out = await self.session.execute(
            select(
                BatterRetirement.innings_id,
                func.count(BatterRetirement.id),
            )
            .where(
                BatterRetirement.match_id == match_id,
                BatterRetirement.status == DeliveryStatus.RECORDED,
                BatterRetirement.retirement_type == RetirementType.OUT,
            )
            .group_by(BatterRetirement.innings_id)
        )

        for innings_id, count in retired_out.all():
            runs, legal_balls, wickets = totals.get(innings_id, (0, 0, 0))
            totals[innings_id] = (runs, legal_balls, wickets + int(count))

        return totals


    async def get_match(self, match_id: UUID) -> Match | None:
        return await self.session.get(Match, match_id)


    @staticmethod
    def delivery_options():
        return (
            joinedload(Delivery.striker),
            joinedload(Delivery.non_striker),
            joinedload(Delivery.bowler),
            joinedload(Delivery.dismissed_player),
            joinedload(Delivery.fielder),
            joinedload(Delivery.next_batter),
            selectinload(Delivery.corrections),
        )


    async def get_recorded_deliveries(self, innings_id: UUID) -> list[Delivery]:
        statement = (
            select(
                Delivery
            )
            .where(
                Delivery.innings_id
                == innings_id,

                Delivery.status
                == DeliveryStatus.RECORDED,
            )
            .options(
                *self.delivery_options()
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
            select(
                Delivery
            )
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


    async def get_delivery_history(self, innings_id: UUID, *, limit: int = 20) -> list[Delivery]:
        """
        Includes void deliveries for
        the Stage 5 correction screen.
        """

        statement = (
            select(
                Delivery
            )
            .where(
                Delivery.innings_id
                == innings_id
            )
            .options(
                *self.delivery_options()
            )
            .order_by(
                Delivery
                .delivery_number
                .desc()
            )
            .limit(
                limit
            )
        )

        result = await self.session.scalars(statement)
        return list(reversed(result.all()))


    async def get_delivery_for_update(self, *, match_id: UUID, delivery_id: UUID) -> Delivery | None:
        statement = (
            select(
                Delivery
            )
            .where(
                Delivery.id
                == delivery_id,

                Delivery.match_id
                == match_id,
            )
            .with_for_update(
                of=Delivery
            )
        )

        return await self.session.scalar(statement)


    async def last_recorded_delivery(self, innings_id: UUID) -> Delivery | None:
        statement = (
            select(
                Delivery
            )
            .where(
                Delivery.innings_id
                == innings_id,

                Delivery.status
                == DeliveryStatus.RECORDED,
            )
            .order_by(
                Delivery
                .delivery_number
                .desc()
            )
            .limit(1)
        )

        return await self.session.scalar(statement)


    async def next_delivery_number(self, innings_id: UUID) -> int:
        """
        Sequence numbers are permanent.

        Example:
        delivery #8 is voided
        -> next event is still #9.
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

        value = await self.session.scalar(statement)
        return int(value or 1)


    async def dismissed_player_ids(self, innings_id: UUID) -> set[UUID]:
        statement = (
            select(
                Delivery
                .dismissed_player_id
            )
            .where(
                Delivery.innings_id
                == innings_id,

                Delivery.status
                == DeliveryStatus.RECORDED,

                Delivery
                .dismissed_player_id
                .is_not(None),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return {
            item
            for item
            in result.all()
            if item is not None
        }


    async def get_player(self, player_id: UUID) -> Player | None:
        return await self.session.get(Player, player_id)


    async def is_playing_team_player(
        self,
        *,
        match_id: UUID,
        team_id: UUID,
        player_id: UUID,
    ) -> bool:

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


    async def get_playing_xi_with_players(self, match_id: UUID, team_id: UUID) -> list[MatchPlayer]:
        statement = (
            select(MatchPlayer)
            .where(
                MatchPlayer.match_id == match_id,
                MatchPlayer.team_id == team_id,
            )
            .options(joinedload(MatchPlayer.player))
            .order_by(
                MatchPlayer.batting_order.asc(),
                MatchPlayer.player_id.asc(),
            )
        )

        result = await self.session.scalars(statement)
        return list(result.all())


    async def get_official_retirements(
        self,
        innings_id: UUID,
        *,
        with_players: bool = False,
    ) -> list[BatterRetirement]:
        """
        Non-void retirements in event order,
        replayed together with deliveries.
        """

        statement = (
            select(BatterRetirement)
            .where(
                BatterRetirement.innings_id == innings_id,
                BatterRetirement.status == DeliveryStatus.RECORDED,
            )
            .order_by(BatterRetirement.event_number.asc())
        )

        if with_players:
            statement = statement.options(
                joinedload(BatterRetirement.player),
                joinedload(BatterRetirement.replacement_player),
            )

        result = await self.session.scalars(statement)
        return list(result.all())


    async def next_retirement_number(self, innings_id: UUID) -> int:
        """
        Like delivery numbers, event numbers
        are permanent and never reused.
        """

        statement = (
            select(func.coalesce(func.max(BatterRetirement.event_number), 0) + 1)
            .where(BatterRetirement.innings_id == innings_id)
        )

        value = await self.session.scalar(statement)
        return int(value or 1)


    async def get_retirement_for_update(
        self,
        *,
        match_id: UUID,
        retirement_id: UUID,
    ) -> BatterRetirement | None:
        statement = (
            select(BatterRetirement)
            .where(
                BatterRetirement.id == retirement_id,
                BatterRetirement.match_id == match_id,
            )
            .with_for_update(of=BatterRetirement)
        )

        return await self.session.scalar(statement)
