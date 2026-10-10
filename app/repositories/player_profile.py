from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.models import (
    Delivery,
    DeliveryStatus,
    Innings,
    Match,
    MatchPlayer,
    PlayerRole,
    Team,
    TeamPlayer,
    TeamStatus,
    WicketType,
)


@dataclass(frozen=True)
class PlayerActivityRow:
    match_id: UUID
    innings_id: UUID
    innings_number: int
    scheduled_at: datetime | None
    match_created_at: datetime
    balls_per_over: int
    striker_id: UUID
    bowler_id: UUID
    batter_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    is_legal_ball: bool
    wicket_type: WicketType | None
    dismissed_player_id: UUID | None


@dataclass(frozen=True)
class TeamMembershipRow:
    team_id: UUID
    team_name: str
    team_short_name: str
    role: PlayerRole
    squad_number: int | None
    joined_on: date | None
    left_on: date | None
    is_active: bool


@dataclass(frozen=True)
class MatchSelectionRow:
    match_id: UUID
    title: str | None
    scheduled_at: datetime | None
    match_created_at: datetime
    player_team_id: UUID
    team_a_id: UUID
    team_a_name: str
    team_b_id: UUID
    team_b_name: str


class PlayerProfileRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    async def active_team_memberships(self, player_id: UUID) -> list[TeamMembershipRow]:
        statement = (
            select(
                TeamPlayer.team_id,
                Team.name,
                Team.short_name,
                TeamPlayer.role,
                TeamPlayer.squad_number,
                TeamPlayer.joined_on,
                TeamPlayer.left_on,
                TeamPlayer.is_active,
            )
            .join(
                Team,
                Team.id ==
                TeamPlayer.team_id,
            )
            .where(
                (
                    TeamPlayer.player_id
                    == player_id
                ),
                TeamPlayer
                .is_active
                .is_(True),
                or_(
                    TeamPlayer
                    .left_on
                    .is_(None),
                    TeamPlayer.left_on
                    >= date.today(),
                ),
                Team.status
                != TeamStatus.ARCHIVED,
            )
            .order_by(
                Team.name.asc()
            )
        )
        rows = (await self.session.execute(statement)).all()
        return [TeamMembershipRow(*row) for row in rows]


    async def activity_rows(self, player_id: UUID, *, match_ids: list[UUID] | None = None) -> list[PlayerActivityRow]:
        statement = (
            select(
                Delivery.match_id,
                Delivery.innings_id,
                Innings.innings_number,
                Match.scheduled_at,
                Match.created_at,
                Match.balls_per_over,
                Delivery.striker_id,
                Delivery.bowler_id,
                Delivery.batter_runs,
                Delivery.wide_runs,
                Delivery.no_ball_runs,
                Delivery.bye_runs,
                Delivery.leg_bye_runs,
                Delivery.is_legal_ball,
                Delivery.wicket_type,
                Delivery.dismissed_player_id,
            )
            .join(
                Innings,
                Innings.id ==
                Delivery.innings_id,
            )
            .join(
                Match,
                Match.id ==
                Delivery.match_id,
            )
            .where(

                Delivery.status
                == DeliveryStatus.RECORDED,

                or_(
                    Delivery.striker_id
                    == player_id,

                    Delivery.bowler_id
                    == player_id,

                    (
                        Delivery
                        .dismissed_player_id
                        == player_id
                    ),
                ),
            )
            .order_by(
                Match.created_at.desc(),
                Innings
                .innings_number
                .desc(),
                Delivery
                .delivery_number
                .asc(),
            )
        )

        if match_ids is not None:

            if not match_ids:
                return []

            statement = statement.where(Delivery.match_id.in_(match_ids))

        rows = (await self.session.execute(statement)).all()
        return [PlayerActivityRow(*row) for row in rows]


    async def match_history_count(self, player_id: UUID) -> int:
        statement = (
            select(
                func.count(
                    MatchPlayer.id
                )
            )
            .where(MatchPlayer.player_id == player_id)
        )
        return int(await self.session.scalar(statement) or 0)


    async def match_history_page(
        self,
        player_id: UUID,
        *,
        page: int,
        page_size: int,
    ) -> list[
        MatchSelectionRow
    ]:

        team_a = aliased(Team)
        team_b = aliased(Team)

        statement = (
            select(
                Match.id,
                Match.title,
                Match.scheduled_at,
                Match.created_at,
                MatchPlayer.team_id,
                Match.team_a_id,
                team_a.name,
                Match.team_b_id,
                team_b.name,
            )
            .join(
                MatchPlayer,
                (
                    MatchPlayer
                    .match_id
                    == Match.id
                ),
            )
            .join(
                team_a,
                team_a.id
                == Match.team_a_id,
            )
            .join(
                team_b,
                team_b.id
                == Match.team_b_id,
            )
            .where(
                MatchPlayer.player_id
                == player_id
            )
            .order_by(
                Match
                .scheduled_at
                .desc()
                .nullslast(),
                Match
                .created_at
                .desc(),
            )
            .offset((page - 1) * page_size)
            .limit(
                page_size
            )
        )

        rows = (await self.session.execute(statement)).all()
        return [MatchSelectionRow(*row) for row in rows]