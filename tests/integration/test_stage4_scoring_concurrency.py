import asyncio
import os
from uuid import uuid4
import pytest
from sqlalchemy import delete, select
from app.db.session import AsyncSessionFactory
from app.models import (
    Delivery,
    Innings,
    Match,
    MatchPlayer,
    Player,
    Team,
)
from app.models.enums import InningsStatus, MatchStatus
from app.schemas.scoring import DeliveryCreate
from app.services.scoring import record_delivery


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv(
        "RUN_LIVE_DB_TESTS"
    ) != "1",

    reason=(
        "Set RUN_LIVE_DB_TESTS=1 "
        "to run the PostgreSQL "
        "row-lock concurrency test"
    ),
)
async def test_concurrent_writes_get_distinct_sequences() -> None:
    suffix = uuid4().hex[:10]

    async with AsyncSessionFactory() as setup_session:
        async with setup_session.begin():
            team_a = Team(
                name=f"Stage4 A {suffix}",
                short_name=f"A{suffix[:4]}",
                code=f"S4A{suffix[:6]}",
            )
            team_b = Team(
                name=f"Stage4 B {suffix}",
                short_name=f"B{suffix[:4]}",
                code=f"S4B{suffix[:6]}",
            )

            setup_session.add_all([team_a, team_b])
            await setup_session.flush()

            a1 = Player(full_name=f"Stage4 A1 {suffix}")
            a2 = Player(full_name=(f"Stage4 A2 {suffix}"))
            b1 = Player(full_name=(f"Stage4 B1 {suffix}"))
            b2 = Player(full_name=(f"Stage4 B2 {suffix}"))

            setup_session.add_all([a1, a2, b1, b2])
            await setup_session.flush()

            match = Match(
                title=(
                    "Stage4 concurrency "
                    f"{suffix}"
                ),
                team_a_id=(team_a.id),
                team_b_id=(team_b.id),
                players_per_side=2,
                total_overs=None,
                balls_per_over=6,
                innings_per_team=1,
                status=(MatchStatus.READY),
            )
            setup_session.add(match)
            await setup_session.flush()
            setup_session.add_all(
                [
                    MatchPlayer(
                        match_id=match.id,
                        team_id=team_a.id,
                        player_id=a1.id,
                        batting_order=1,
                    ),
                    MatchPlayer(
                        match_id=match.id,
                        team_id=team_a.id,
                        player_id=a2.id,
                        batting_order=2,
                    ),
                    MatchPlayer(
                        match_id=match.id,
                        team_id=team_b.id,
                        player_id=b1.id,
                        batting_order=1,
                    ),
                    MatchPlayer(
                        match_id=match.id,
                        team_id=team_b.id,
                        player_id=b2.id,
                        batting_order=2,
                    ),
                ]
            )


            innings = Innings(
                match_id=match.id,
                innings_number=1,
                batting_team_id=team_a.id,
                bowling_team_id=team_b.id,
                status=InningsStatus.PENDING,
                striker_id=a1.id,
                non_striker_id=a2.id,
                current_bowler_id=b1.id
            )
            setup_session.add(innings)
            await setup_session.flush()

            match_id = match.id
            innings_id = innings.id
            team_ids = [team_a.id, team_b.id]
            player_ids = [a1.id, a2.id, b1.id, b2.id]


    async def score_once(runs: int):
        async with AsyncSessionFactory()as session:
            return await record_delivery(
                session,
                match_id,
                DeliveryCreate(runs=runs),
            )

    try:
        first, second = await asyncio.gather(score_once(1), score_once(2))
        async with AsyncSessionFactory() as verify_session:
            result = (
                await verify_session
                .scalars(
                    select(
                        Delivery
                    )
                    .where(
                        Delivery.innings_id
                        == innings_id
                    )
                    .order_by(
                        Delivery
                        .delivery_number
                        .asc()
                    )
                )
            )
            deliveries = list(result.all())

        assert [item.delivery_number for item in deliveries] == [1, 2]
        assert sum(item.total_runs for item in deliveries) == 3
        assert {first.legal_balls, second.legal_balls} == {1, 2}
        assert max(first.total_runs, second.total_runs) == 3


    finally:
        async with AsyncSessionFactory() as cleanup_session:
            async with cleanup_session.begin():
                await cleanup_session.execute(
                    delete(Match)
                    .where(Match.id == match_id)
                )
                await cleanup_session.execute(
                    delete(Team)
                    .where(Team.id.in_(team_ids))
                )
                await cleanup_session.execute(
                    delete(Player)
                    .where(Player.id.in_(player_ids))
                )