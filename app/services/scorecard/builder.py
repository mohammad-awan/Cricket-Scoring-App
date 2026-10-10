from __future__ import annotations
from collections import defaultdict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError
from app.models.enums import InningsStatus, MatchStatus
from app.repositories.scorecard import MatchPlayerRow, ScorecardRepository
from app.schemas.match_setup import TeamSummary
from app.schemas.scorecard import (
    FullScorecardRead,
    InningsScorecardRead,
    MatchLifecycleRead,
    MatchResultRead,
)
from app.services.scorecard.batting import batting_scorecard
from app.services.scorecard.bowling import bowling_scorecard
from app.services.scorecard.chase import chase_metrics
from app.services.scorecard.extras import extras_summary
from app.services.scorecard.formatters import overs_display, run_rate
from app.services.scorecard.innings import innings_totals
from app.services.scorecard.partnerships import partnership_scorecard
from app.services.scorecard.result import result_summary, state_label


async def get_full_scorecard(
    session: AsyncSession,
    match_id: UUID,
) -> FullScorecardRead:

    repository = (
        ScorecardRepository(
            session
        )
    )

    match = (
        await repository
        .get_match(
            match_id
        )
    )

    if match is None:

        raise NotFoundError(
            "Match not found"
        )

    innings_list = (
        await repository
        .list_innings(
            match_id
        )
    )

    match_players = (
        await repository
        .list_match_players(
            match_id
        )
    )

    players_by_team: dict[
        UUID,
        list[
            MatchPlayerRow
        ],
    ] = defaultdict(
        list
    )

    for player in match_players:

        players_by_team[
            player.team_id
        ].append(
            player
        )

    innings_cards: list[
        InningsScorecardRead
    ] = []

    for innings in innings_list:

        deliveries = (
            await repository
            .list_delivery_rows(
                innings.id
            )
        )

        totals = (
            innings_totals(
                deliveries
            )
        )

        innings_cards.append(
            InningsScorecardRead(
                innings_id=(
                    innings.id
                ),

                innings_number=(
                    innings
                    .innings_number
                ),

                status=(
                    innings.status
                ),

                batting_team=(
                    TeamSummary
                    .model_validate(
                        innings
                        .batting_team
                    )
                ),

                bowling_team=(
                    TeamSummary
                    .model_validate(
                        innings
                        .bowling_team
                    )
                ),

                total_runs=(
                    totals.runs
                ),

                wickets=(
                    totals.wickets
                ),

                legal_balls=(
                    totals.legal_balls
                ),

                overs=(
                    overs_display(
                        totals
                        .legal_balls,

                        match
                        .balls_per_over,
                    )
                ),

                run_rate=(
                    run_rate(
                        totals.runs,

                        totals
                        .legal_balls,

                        match
                        .balls_per_over,
                    )
                ),

                extras=(
                    extras_summary(
                        deliveries
                    )
                ),

                batting=(
                    batting_scorecard(
                        players=(
                            players_by_team[
                                innings
                                .batting_team_id
                            ]
                        ),

                        deliveries=(
                            deliveries
                        ),
                    )
                ),

                bowling=(
                    bowling_scorecard(
                        deliveries=(
                            deliveries
                        ),

                        balls_per_over=(
                            match
                            .balls_per_over
                        ),
                    )
                ),

                partnerships=(
                    partnership_scorecard(
                        deliveries
                    )
                ),
            )
        )

    current_innings = (
        innings_list[-1]

        if innings_list

        else None
    )

    current_card = (
        innings_cards[-1]

        if innings_cards

        else None
    )

    max_innings = (
        match.innings_per_team
        * 2
    )

    can_start_next = (
        current_innings
        is not None

        and current_innings.status
        == InningsStatus.COMPLETED

        and current_innings
        .innings_number
        < max_innings

        and match.status
        not in {
            MatchStatus.COMPLETED,
            MatchStatus.ABANDONED,
        }
    )

    can_score = (
        current_innings
        is not None

        and match.status
        in {
            MatchStatus.READY,
            MatchStatus.LIVE,
        }

        and current_innings.status
        in {
            InningsStatus.PENDING,
            InningsStatus.LIVE,
        }
    )

    winner_team = (
        TeamSummary
        .model_validate(
            match.winner_team
        )

        if (
            match.winner_team
            is not None
        )

        else None
    )

    lifecycle = (
        MatchLifecycleRead(
            match_id=(
                match.id
            ),

            status=(
                match.status
            ),

            current_innings_number=(
                current_innings
                .innings_number

                if (
                    current_innings
                    is not None
                )

                else None
            ),

            state_label=(
                state_label(
                    match,
                    current_innings,
                )
            ),

            can_score=(
                can_score
            ),

            can_start_next_innings=(
                can_start_next
            ),

            chase=(
                chase_metrics(
                    match=match,

                    innings_cards=(
                        innings_cards
                    ),

                    current=(
                        current_card
                    ),
                )
            ),

            result=(
                MatchResultRead(
                    completed=(
                        match.status
                        == MatchStatus
                        .COMPLETED
                    ),

                    winner_team=(
                        winner_team
                    ),

                    result_type=(
                        match
                        .result_type
                    ),

                    result_margin=(
                        match
                        .result_margin
                    ),

                    summary=(
                        result_summary(
                            match
                        )
                    ),

                    completed_at=(
                        match
                        .completed_at
                    ),
                )
            ),
        )
    )

    return FullScorecardRead(
        match_id=(
            match.id
        ),

        title=(
            match.title
        ),

        status=(
            match.status
        ),

        team_a=(
            TeamSummary
            .model_validate(
                match.team_a
            )
        ),

        team_b=(
            TeamSummary
            .model_validate(
                match.team_b
            )
        ),

        total_overs=(
            match.total_overs
        ),

        balls_per_over=(
            match.balls_per_over
        ),

        innings_per_team=(
            match.innings_per_team
        ),

        innings=(
            innings_cards
        ),

        lifecycle=(
            lifecycle
        ),
    )
