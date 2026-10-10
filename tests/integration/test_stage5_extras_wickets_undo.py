import os
from uuid import uuid4
import pytest
from sqlalchemy import delete, select
from app.core.exceptions import ValidationError
from app.db.session import AsyncSessionFactory
from app.models import (
    Delivery,
    DeliveryCorrection,
    Innings,
    Match,
    MatchPlayer,
    Player,
    Team,
)
from app.models.enums import (
    DeliveryStatus,
    InningsStatus,
    MatchStatus,
    WicketType,
)
from app.schemas.scoring import (
    DeliveryCreate,
    DeliveryUndo,
    WicketCreate,
)
from app.services.scoring import (
    get_scoring_state,
    record_delivery,
    undo_delivery,
)


pytestmark = pytest.mark.integration


async def _record(match_id, payload):
    async with AsyncSessionFactory() as session:
        return await record_delivery(session, match_id, payload)


async def _undo(match_id, delivery_id, reason=("Stage 5 correction")):
    async with AsyncSessionFactory() as session:
        return await undo_delivery(
            session,
            match_id,
            delivery_id,
            DeliveryUndo(
                reason=reason
            ),
        )


async def _state(match_id):
    async with AsyncSessionFactory() as session:
        return await get_scoring_state(session, match_id)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_TESTS") != "1",
    reason=(
        "Set RUN_LIVE_DB_TESTS=1 "
        "to run the PostgreSQL "
        "Stage 5 flow test"
    ),
)
async def test_extras_wicket_failed_transaction_and_undo() -> None:
    suffix = uuid4().hex[:10]
    async with AsyncSessionFactory() as setup_session:
        async with setup_session.begin():
            team_a = Team(
                name=(
                    f"Stage5 A "
                    f"{suffix}"
                ),
                short_name=(f"A{suffix[:4]}"),
                code=(f"S5A{suffix[:6]}"),
            )
            team_b = Team(
                name=(
                    f"Stage5 B "
                    f"{suffix}"
                ),
                short_name=(
                    f"B{suffix[:4]}"
                ),
                code=(
                    f"S5B{suffix[:6]}"
                ),
            )
            setup_session.add_all([team_a, team_b])
            await setup_session.flush()
            a1 = Player(
                full_name=(
                    f"Stage5 A1 "
                    f"{suffix}"
                )
            )
            a2 = Player(
                full_name=(
                    f"Stage5 A2 "
                    f"{suffix}"
                )
            )
            a3 = Player(
                full_name=(
                    f"Stage5 A3 "
                    f"{suffix}"
                )
            )
            b1 = Player(
                full_name=(
                    f"Stage5 B1 "
                    f"{suffix}"
                )
            )
            b2 = Player(
                full_name=(
                    f"Stage5 B2 "
                    f"{suffix}"
                )
            )
            b3 = Player(
                full_name=(
                    f"Stage5 B3 "
                    f"{suffix}"
                )
            )
            setup_session.add_all([a1, a2, a3, b1, b2, b3])
            await setup_session.flush()
            match = Match(
                title=(
                    f"Stage5 flow "
                    f"{suffix}"
                ),
                team_a_id=(team_a.id),
                team_b_id=(team_b.id),
                players_per_side=3,
                total_overs=2,
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
                        team_id=team_a.id,
                        player_id=a3.id,
                        batting_order=3,
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
                    MatchPlayer(
                        match_id=match.id,
                        team_id=team_b.id,
                        player_id=b3.id,
                        batting_order=3,
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
                current_bowler_id=b1.id,
            )
            setup_session.add(innings)
            await setup_session.flush()
            match_id = (match.id)
            team_ids = [team_a.id, team_b.id]
            player_ids = [a1.id, a2.id, a3.id, b1.id, b2.id, b3.id]

    try:
        # =====================
        # WIDE
        # =====================
        state = await _record(
            match_id,
            DeliveryCreate(
                wide_runs=1
            ),
        )
        assert state.total_runs == 1
        assert state.legal_balls == 0
        assert state.overs == "0.0"
        assert state.striker.id == a1.id
        # =====================
        # NO BALL + 1 BATTER RUN
        # =====================
        state = await _record(
            match_id,
            DeliveryCreate(
                runs=1,
                no_ball=True,
            ),
        )
        assert state.total_runs == 3
        assert state.legal_balls == 0
        assert state.striker.id == a2.id
        # ===================
        # BYE
        # ====================
        state = await _record(
            match_id,
            DeliveryCreate(
                bye_runs=1
            ),
        )
        assert state.total_runs == 4
        assert state.legal_balls == 1
        assert state.striker.id == a1.id
        assert state.next_sequence == 4
        # =====================
        # INVALID WICKET
        # =====================
        with pytest.raises(ValidationError):
            await _record(
                match_id,

                DeliveryCreate(
                    no_ball=True,

                    wicket=(
                        WicketCreate(
                            wicket_type=(
                                WicketType
                                .BOWLED
                            ),

                            dismissed_player_id=(
                                a1.id
                            ),

                            selection_mode="manual",


                            next_batter_id=(
                                a3.id
                            ),
                        )
                    ),
                ),
            )

        # Failed event must leave
        # no partial state.
        state = await _state(
            match_id
        )
        assert state.total_runs == 4
        assert state.legal_balls == 1
        assert state.wickets == 0
        assert state.next_sequence == 4
        # =====================
        # VALID WICKET
        # =====================
        state = await _record(
            match_id,
            DeliveryCreate(
                wicket=(
                    WicketCreate(
                        wicket_type=(
                            WicketType
                            .BOWLED
                        ),

                        dismissed_player_id=(
                            a1.id
                        ),

                        selection_mode="manual",


                        next_batter_id=(
                            a3.id
                        ),
                    )
                )
            ),
        )
        assert state.total_runs == 4
        assert state.legal_balls == 2
        assert state.wickets == 1
        assert state.striker.id == a3.id
        assert (
            a1.id
            in state
            .dismissed_player_ids
        )
        wicket_delivery = (
            state
            .recent_deliveries[-1]
        )
        assert (
            wicket_delivery
            .wicket_type
            == WicketType.BOWLED
        )
        assert (
            wicket_delivery
            .dismissed_player
            .id
            == a1.id
        )
        # =====================
        # UNDO
        # =====================
        state = await _undo(match_id, wicket_delivery.id)
        assert state.total_runs  == 4
        assert state.legal_balls == 1
        assert state.wickets == 0
        assert state.striker.id == a1.id
        assert state.non_striker.id == a2.id
        # Sequence number 4 stays
        # permanently reserved.
        assert state.next_sequence == 5
        assert state.cache_matches_history
        # =====================
        # DATABASE AUDIT
        # =====================
        async with AsyncSessionFactory() as verify_session:
            delivery = (
                await verify_session
                .scalar(
                    select(
                        Delivery
                    )
                    .where(
                        Delivery.id
                        == wicket_delivery.id
                    )
                )
            )
            correction = (
                await verify_session
                .scalar(
                    select(
                        DeliveryCorrection
                    )
                    .where(
                        DeliveryCorrection
                        .delivery_id
                        == wicket_delivery.id
                    )
                )
            )
        assert delivery is not None
        assert delivery.status == DeliveryStatus.VOID
        assert correction is not None
        assert correction.reason == "Stage 5 correction"

    finally:
        async with AsyncSessionFactory() as cleanup_session:
            async with cleanup_session.begin():

                await cleanup_session.execute(
                    delete(
                        Match
                    )
                    .where(
                        Match.id
                        == match_id
                    )
                )
                await cleanup_session.execute(
                    delete(
                        Team
                    )
                    .where(
                        Team.id.in_(
                            team_ids
                        )
                    )
                )
                await cleanup_session.execute(
                    delete(
                        Player
                    )
                    .where(
                        Player.id.in_(
                            player_ids
                        )
                    )
                )