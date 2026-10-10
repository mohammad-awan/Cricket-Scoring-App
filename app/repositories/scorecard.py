from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload
from app.models import (
    BatterRetirement,
    Delivery,
    Innings,
    Match,
    MatchPlayer,
    Player,
)
from app.models.enums import DeliveryStatus


@dataclass(frozen=True)
class MatchPlayerRow:
    team_id: UUID
    player_id: UUID
    full_name: str
    short_name: str | None
    batting_order: int | None


@dataclass(frozen=True)
class DeliveryScoreRow:
    id: UUID
    delivery_number: int
    over_number: int
    ball_number: int
    striker_id: UUID
    striker_name: str
    striker_short_name: str | None
    non_striker_id: UUID
    non_striker_name: str
    non_striker_short_name: str | None
    bowler_id: UUID
    bowler_name: str
    bowler_short_name: str | None
    batter_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    total_runs: int
    is_legal_ball: bool
    wicket_type: str | None
    dismissed_player_id: UUID | None
    dismissed_player_name: str | None
    dismissed_player_short_name: str | None
    fielder_id: UUID | None
    fielder_name: str | None
    fielder_short_name: str | None
    next_batter_id: UUID | None


@dataclass(frozen=True)
class RetirementScoreRow:
    event_number: int
    after_delivery_number: int
    player_id: UUID
    retirement_type: str
    replacement_player_id: UUID | None


class ScorecardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    async def get_match(self, match_id: UUID) -> Match | None:
        statement = (
            select(
                Match
            )
            .where(
                Match.id
                == match_id
            )
            .options(
                joinedload(Match.team_a),
                joinedload(Match.team_b),
                joinedload(Match.winner_team),
            )
        )

        return await self.session.scalar(statement)


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

        result = (
            await self.session
            .scalars(statement)
        )

        return list(result.all())


    async def list_match_players(self, match_id: UUID) -> list[MatchPlayerRow]:
        statement = (
            select(
                MatchPlayer.team_id,
                MatchPlayer.player_id,
                Player.full_name,
                Player.short_name,
                MatchPlayer.batting_order,
            )
            .join(
                Player,
                Player.id
                == MatchPlayer.player_id,
            )
            .where(MatchPlayer.match_id == match_id)
            .order_by(
                MatchPlayer
                .team_id
                .asc(),
                MatchPlayer
                .batting_order
                .asc()
                .nulls_last(),
                Player
                .full_name
                .asc(),
            )
        )
        rows = (
            await self.session
            .execute(
                statement
            )
        ).all()

        return [
            MatchPlayerRow(
                team_id=(row.team_id),
                player_id=(row.player_id),
                full_name=(row.full_name),
                short_name=(row.short_name),
                batting_order=(row.batting_order),
            )

            for row in rows
        ]


    async def list_delivery_rows(self, innings_id: UUID) -> list[DeliveryScoreRow]:
        striker = aliased(Player)
        non_striker = aliased(Player)
        bowler = aliased(Player)
        dismissed = aliased(Player)
        fielder = aliased(Player)

        statement = (
            select(
                Delivery.id,
                Delivery
                .delivery_number,
                Delivery
                .over_number,
                Delivery
                .ball_number,
                Delivery
                .striker_id,

                striker
                .full_name
                .label(
                    "striker_name"
                ),
                striker
                .short_name
                .label(
                    "striker_short_name"
                ),
                Delivery
                .non_striker_id,
                non_striker
                .full_name
                .label(
                    "non_striker_name"
                ),
                non_striker
                .short_name
                .label("non_striker_short_name"),
                Delivery
                .bowler_id,
                bowler
                .full_name
                .label("bowler_name"),
                bowler
                .short_name
                .label("bowler_short_name"),
                Delivery
                .batter_runs,
                Delivery
                .wide_runs,
                Delivery
                .no_ball_runs,
                Delivery
                .bye_runs,
                Delivery
                .leg_bye_runs,
                Delivery
                .total_runs,
                Delivery
                .is_legal_ball,
                Delivery
                .wicket_type,
                Delivery
                .dismissed_player_id,
                dismissed
                .full_name
                .label("dismissed_player_name"),
                dismissed
                .short_name
                .label("dismissed_player_short_name"),
                Delivery
                .fielder_id,
                fielder
                .full_name
                .label(
                    "fielder_name"
                ),
                fielder
                .short_name
                .label(
                    "fielder_short_name"
                ),
                Delivery
                .next_batter_id,
            )
            .join(
                striker,
                striker.id
                == Delivery.striker_id,
            )
            .join(
                non_striker,
                non_striker.id
                == Delivery.non_striker_id,
            )
            .join(
                bowler,
                bowler.id
                == Delivery.bowler_id,
            )
            .outerjoin(
                dismissed,
                dismissed.id
                == Delivery
                .dismissed_player_id,
            )
            .outerjoin(
                fielder,
                fielder.id
                == Delivery.fielder_id,
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
        rows = (
            await self.session
            .execute(statement)
        ).all()

        return [
            DeliveryScoreRow(
                id=row.id,
                delivery_number=(row.delivery_number),
                over_number=(row.over_number),
                ball_number=(row.ball_number),
                striker_id=(row.striker_id),
                striker_name=(row.striker_name),
                striker_short_name=(row.striker_short_name),
                non_striker_id=(row.non_striker_id),
                non_striker_name=(row.non_striker_name),
                non_striker_short_name=(row.non_striker_short_name),
                bowler_id=(row.bowler_id),
                bowler_name=(row.bowler_name),
                bowler_short_name=(row.bowler_short_name),
                batter_runs=(row.batter_runs),
                wide_runs=(row.wide_runs),
                no_ball_runs=(row.no_ball_runs),
                bye_runs=(row.bye_runs),
                leg_bye_runs=(row.leg_bye_runs),
                total_runs=(row.total_runs),
                is_legal_ball=(row.is_legal_ball),
                wicket_type=(
                    row.wicket_type.value
                    if (
                        row.wicket_type
                        is not None
                    )
                    else None
                ),
                dismissed_player_id=(row.dismissed_player_id),
                dismissed_player_name=(row.dismissed_player_name),
                dismissed_player_short_name=(row.dismissed_player_short_name),
                fielder_id=(row.fielder_id),
                fielder_name=(row.fielder_name),
                fielder_short_name=(row.fielder_short_name),
                next_batter_id=(row.next_batter_id),
            )

            for row in rows
        ]


    async def list_retirement_rows(self, innings_id: UUID) -> list[RetirementScoreRow]:
        statement = (
            select(
                BatterRetirement.event_number,
                BatterRetirement.after_delivery_number,
                BatterRetirement.player_id,
                BatterRetirement.retirement_type,
                BatterRetirement.replacement_player_id,
            )
            .where(
                BatterRetirement.innings_id == innings_id,
                BatterRetirement.status == DeliveryStatus.RECORDED,
            )
            .order_by(BatterRetirement.event_number.asc())
        )

        result = await self.session.execute(statement)

        return [
            RetirementScoreRow(
                event_number=row.event_number,
                after_delivery_number=row.after_delivery_number,
                player_id=row.player_id,
                retirement_type=row.retirement_type.value,
                replacement_player_id=row.replacement_player_id,
            )
            for row in result.all()
        ]
