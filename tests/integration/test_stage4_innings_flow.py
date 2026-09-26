import os
from uuid import uuid4
import pytest
from sqlalchemy import delete
from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionFactory
from app.models import (
    Innings,
    Match,
    MatchPlayer,
    Player,
    Team,
)
from app.models.enums import InningsStatus, MatchStatus
from app.schemas.scoring import BowlerChange, DeliveryCreate, NextInningsCreate
from app.services.scoring import (
    change_bowler,
    get_scoring_state,
    record_delivery,
    start_next_innings,
)


pytestmark = pytest.mark.integration


async def _record(match_id, runs):
    async with AsyncSessionFactory() as session:
        return await record_delivery(session, match_id, DeliveryCreate(runs=runs))


async def _change_bowler(match_id, bowler_id):
    async with AsyncSessionFactory() as session:
        return await change_bowler(session, match_id, BowlerChange(bowler_id=bowler_id))


async def _start_next(match_id, striker_id, non_striker_id, bowler_id):
    async with AsyncSessionFactory() as session:
        return await start_next_innings(
            session,
            match_id,
            NextInningsCreate(
                striker_id=striker_id,
                non_striker_id=non_striker_id,
                opening_bowler_id=bowler_id,
            ),
        )


async def _state(match_id):
    async with AsyncSessionFactory() as session:
        return await get_scoring_state(session, match_id)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv(
        "RUN_LIVE_DB_TESTS"
    ) != "1",

    reason=(
        "Set RUN_LIVE_DB_TESTS=1 "
        "to run the PostgreSQL "
        "innings flow test"
    ),
)
async def test_two_over_match_bowler_rotation_and_second_innings() -> None:
    suffix = uuid4().hex[:10]

    async with AsyncSessionFactory() as setup_session:
        async with setup_session.begin():
            team_a = Team(
                name=f"Stage4 Flow A {suffix}",
                short_name=f"A{suffix[:4]}",
                code=f"F4A{suffix[:6]}",
            )
            team_b = Team(
                name=f"Stage4 Flow B {suffix}",
                short_name=f"B{suffix[:4]}",
                code=f"F4B{suffix[:6]}",
            )
            setup_session.add_all([team_a, team_b])
            await setup_session.flush()

            a1 = Player(full_name=f"Stage4 Flow A1 {suffix}")
            a2 = Player(full_name=f"Stage4 Flow A2 {suffix}")
            b1 = Player(full_name=f"Stage4 Flow B1 {suffix}")
            b2 = Player(full_name=f"Stage4 Flow B2 {suffix}")
            setup_session.add_all([a1, a2, b1, b2])
            await setup_session.flush()

            match = Match(
                title=f"Stage4 innings flow {suffix}",
                team_a_id=team_a.id,
                team_b_id=team_b.id,
                players_per_side=2,
                total_overs=2,
                balls_per_over=6,
                innings_per_team=1,
                status=MatchStatus.READY,
            )
            setup_session.add(match)
            await setup_session.flush()

            setup_session.add_all(
                [
                    MatchPlayer(match_id=match.id, team_id=team_a.id, player_id=a1.id, batting_order=1),
                    MatchPlayer(match_id=match.id, team_id=team_a.id, player_id=a2.id, batting_order=2),
                    MatchPlayer(match_id=match.id, team_id=team_b.id, player_id=b1.id, batting_order=1),
                    MatchPlayer(match_id=match.id, team_id=team_b.id, player_id=b2.id, batting_order=2),
                ]
            )
            setup_session.add(
                Innings(
                    match_id=match.id,
                    innings_number=1,
                    batting_team_id=team_a.id,
                    bowling_team_id=team_b.id,
                    status=InningsStatus.PENDING,
                    striker_id=a1.id,
                    non_striker_id=a2.id,
                    current_bowler_id=b1.id,
                )
            )
            await setup_session.flush()

            match_id = match.id
            team_ids = [team_a.id, team_b.id]
            player_ids = [a1.id, a2.id, b1.id, b2.id]

    try:
        # ---------- Over 1 ----------
        for _ in range(6):
            state = await _record(match_id, 1)

        assert state.bowler_change_required
        assert state.previous_over_bowler_id == b1.id

        # Problem 1: same bowler cannot
        # continue into the next over.
        with pytest.raises(ConflictError):
            await _record(match_id, 0)

        with pytest.raises(ValidationError):
            await _change_bowler(match_id, b1.id)

        state = await _change_bowler(match_id, b2.id)
        assert not state.bowler_change_required
        assert state.current_bowler.id == b2.id

        # ---------- Over 2: innings ends ----------
        for _ in range(6):
            state = await _record(match_id, 0)

        assert state.total_runs == 6
        assert state.overs == "2.0"
        assert state.innings_complete
        assert state.innings_status == InningsStatus.COMPLETED
        assert state.match_status == MatchStatus.INNINGS_BREAK
        assert state.can_start_next_innings
        assert state.next_innings_number == 2
        assert state.next_batting_team.id == team_b.id
        # Innings over, so no bowler prompt.
        assert not state.bowler_change_required

        with pytest.raises(ConflictError):
            await _record(match_id, 1)

        # Openers must come from the
        # correct sides.
        with pytest.raises(ValidationError):
            await _start_next(match_id, a1.id, a2.id, b1.id)

        # ---------- Problem 2: second innings ----------
        state = await _start_next(match_id, b1.id, b2.id, a1.id)

        assert state.innings_number == 2
        assert state.batting_team.id == team_b.id
        assert state.match_status == MatchStatus.LIVE
        assert state.total_runs == 0
        assert state.target == 7
        assert state.runs_required == 7
        assert state.balls_remaining == 12
        assert [item.total_runs for item in state.innings] == [6, 0]

        with pytest.raises(ConflictError):
            await _start_next(match_id, b1.id, b2.id, a1.id)

        # ---------- Chase ends the match ----------
        state = await _record(match_id, 4)
        assert state.runs_required == 3
        assert not state.innings_complete

        state = await _record(match_id, 4)
        assert state.innings_complete
        assert state.match_status == MatchStatus.COMPLETED
        assert state.result_summary == f"{team_b.name} won by 1 wicket"
        assert not state.can_start_next_innings

        with pytest.raises(ConflictError):
            await _record(match_id, 1)

        with pytest.raises(ConflictError):
            await _start_next(match_id, a1.id, a2.id, b1.id)

        # Reading a finished match still works.
        state = await _state(match_id)
        assert state.cache_matches_history
        assert state.result_summary is not None

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
