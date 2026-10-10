import asyncio
import os
from uuid import uuid4
import pytest
from sqlalchemy import delete
from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionFactory
from app.models import Innings, Match, MatchPlayer, Player, Team
from app.models.enums import InningsStatus, MatchStatus, RetirementType, WicketType
from app.schemas.batting_order import LiveBattingOrderUpdate
from app.schemas.retirements import RetirementCreate, RetirementUndo
from app.schemas.scoring import DeliveryCreate, DeliveryUndo, WicketCreate
from app.services.scorecard import get_full_scorecard
from app.services.scoring import (
    create_retirement,
    get_live_batting_order,
    rearrange_batting_order,
    record_delivery,
    undo_delivery,
    undo_retirement,
)


pytestmark = pytest.mark.integration


async def _lineup(match_id):
    async with AsyncSessionFactory() as session:
        return await get_live_batting_order(session, match_id)


async def _rearrange(match_id, ordered_ids):
    async with AsyncSessionFactory() as session:
        return await rearrange_batting_order(
            session,
            match_id,
            LiveBattingOrderUpdate(ordered_player_ids=ordered_ids, reason="Promote hitter"),
        )


async def _retire(match_id, player_id, kind, **selection):
    async with AsyncSessionFactory() as session:
        return await create_retirement(
            session,
            match_id,
            RetirementCreate(
                player_id=player_id,
                retirement_type=kind,
                reason="Stage 10 retirement",
                **selection,
            ),
        )


async def _undo_retirement(match_id, retirement_id):
    async with AsyncSessionFactory() as session:
        return await undo_retirement(
            session,
            match_id,
            retirement_id,
            RetirementUndo(reason="Stage 10 correction"),
        )


async def _record(match_id, payload):
    async with AsyncSessionFactory() as session:
        return await record_delivery(session, match_id, payload)


async def _undo_delivery(match_id, delivery_id):
    async with AsyncSessionFactory() as session:
        return await undo_delivery(
            session,
            match_id,
            delivery_id,
            DeliveryUndo(reason="Stage 10 correction"),
        )


async def _scorecard(match_id):
    async with AsyncSessionFactory() as session:
        return await get_full_scorecard(session, match_id)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_TESTS") != "1",
    reason="Set RUN_LIVE_DB_TESTS=1 to run the PostgreSQL Stage 10 retirement flow test",
)
async def test_live_batting_order_and_retirements() -> None:
    suffix = uuid4().hex[:10]

    async with AsyncSessionFactory() as setup_session:
        async with setup_session.begin():
            team_a = Team(name=f"Stage10 A {suffix}", short_name=f"A{suffix[:4]}", code=f"TA{suffix[:6]}")
            team_b = Team(name=f"Stage10 B {suffix}", short_name=f"B{suffix[:4]}", code=f"TB{suffix[:6]}")
            setup_session.add_all([team_a, team_b])
            await setup_session.flush()

            batters = [Player(full_name=f"Stage10 A{index} {suffix}") for index in range(1, 5)]
            bowlers = [Player(full_name=f"Stage10 B{index} {suffix}") for index in range(1, 5)]
            setup_session.add_all([*batters, *bowlers])
            await setup_session.flush()

            # 4 per side -> 3 wickets end the innings.
            match = Match(
                title=f"Stage10 retirements {suffix}",
                team_a_id=team_a.id,
                team_b_id=team_b.id,
                players_per_side=4,
                total_overs=5,
                balls_per_over=6,
                innings_per_team=1,
                status=MatchStatus.READY,
            )
            setup_session.add(match)
            await setup_session.flush()

            setup_session.add_all(
                [
                    MatchPlayer(match_id=match.id, team_id=team.id, player_id=player.id, batting_order=index)
                    for team, squad in ((team_a, batters), (team_b, bowlers))
                    for index, player in enumerate(squad, start=1)
                ]
            )
            setup_session.add(
                Innings(
                    match_id=match.id,
                    innings_number=1,
                    batting_team_id=team_a.id,
                    bowling_team_id=team_b.id,
                    status=InningsStatus.PENDING,
                    striker_id=batters[0].id,
                    non_striker_id=batters[1].id,
                    current_bowler_id=bowlers[0].id,
                )
            )
            await setup_session.flush()

            match_id = match.id
            team_ids = [team_a.id, team_b.id]
            player_ids = [player.id for player in (*batters, *bowlers)]

    a1, a2, a3, a4 = (player.id for player in batters)
    b1 = bowlers[0].id

    try:
        # =====================
        # LIVE BATTING ORDER
        # =====================
        lineup = await _lineup(match_id)
        assert lineup.next_automatic_batter_id == a3
        assert [entry.locked for entry in lineup.entries] == [True, True, False, False]

        with pytest.raises(ValidationError):
            await _rearrange(match_id, [a1, a4])

        # Two scorers at once: the innings lock serialises them.
        results = await asyncio.gather(
            _rearrange(match_id, [a4, a3]),
            _rearrange(match_id, [a3, a4]),
            return_exceptions=True,
        )
        assert not any(isinstance(result, Exception) for result in results)

        lineup = await _rearrange(match_id, [a4, a3])
        assert lineup.next_automatic_batter_id == a4
        assert {entry.player.id: entry.batting_order for entry in lineup.entries}[a4] == 3

        # =====================
        # RETIRED HURT (striker, before first ball)
        # =====================
        state = await _retire(match_id, a1, RetirementType.HURT)
        assert state.striker.id == a4
        assert state.non_striker.id == a2
        assert state.wickets == 0
        assert state.retired_hurt_player_ids == [a1]
        hurt_id = state.retirements[-1].id

        state = await _record(match_id, DeliveryCreate(runs=0))
        assert state.striker.id == a4
        dot_ball_id = state.recent_deliveries[-1].id

        # =====================
        # RETIRED OUT (non-striker)
        # =====================
        state = await _retire(match_id, a2, RetirementType.OUT)
        assert state.non_striker.id == a3
        assert state.wickets == 1
        assert a2 in state.dismissed_player_ids
        assert state.retirement_blocks_undo
        out_id = state.retirements[-1].id

        # The delivery before a retirement cannot be undone first.
        with pytest.raises(ConflictError):
            await _undo_delivery(match_id, dot_ball_id)

        # An older retirement cannot be undone out of order.
        with pytest.raises(ConflictError):
            await _undo_retirement(match_id, hurt_id)

        state = await _undo_retirement(match_id, out_id)
        assert state.wickets == 0
        assert state.non_striker.id == a2
        assert not state.retirement_blocks_undo

        # =====================
        # RETIRED HURT BATTER RESUMES AT A WICKET
        # =====================
        state = await _record(
            match_id,
            DeliveryCreate(
                wicket=WicketCreate(
                    wicket_type=WicketType.BOWLED,
                    selection_mode="manual",
                    next_batter_id=a1,
                )
            ),
        )
        assert state.striker.id == a1
        assert state.wickets == 1
        assert state.retired_hurt_player_ids == []

        state = await _retire(match_id, a2, RetirementType.OUT)
        assert state.non_striker.id == a3
        assert state.wickets == 2

        # =====================
        # FINAL WICKET BY RETIREMENT, THEN UNDO
        # =====================
        state = await _retire(match_id, a1, RetirementType.OUT)
        assert state.wickets == 3
        assert state.innings_complete
        final_id = state.retirements[-1].id

        state = await _undo_retirement(match_id, final_id)
        assert state.wickets == 2
        assert not state.innings_complete
        assert state.innings_status == InningsStatus.LIVE
        assert state.striker.id == a1

        # =====================
        # SCORECARD
        # =====================
        card = (await _scorecard(match_id)).innings[0]
        batting = {row.player.id: row for row in card.batting}

        assert card.wickets == 2
        assert batting[a2].dismissal == "retired out"
        assert not batting[a2].is_not_out
        assert batting[a1].dismissal == "not out"
        assert batting[a4].dismissal.startswith("b ")

        bowling = {row.player.id: row for row in card.bowling}
        # Retired out never credits the bowler.
        assert bowling[b1].wickets == 1

    finally:
        async with AsyncSessionFactory() as cleanup_session:
            async with cleanup_session.begin():
                await cleanup_session.execute(delete(Match).where(Match.id == match_id))
                await cleanup_session.execute(delete(Team).where(Team.id.in_(team_ids)))
                await cleanup_session.execute(delete(Player).where(Player.id.in_(player_ids)))
