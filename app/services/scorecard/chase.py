from __future__ import annotations
from uuid import UUID
from app.models import Match
from app.schemas.scorecard import ChaseRead, InningsScorecardRead
from app.services.scorecard.formatters import required_run_rate


def team_prior_runs(
    *,
    innings_cards: list[
        InningsScorecardRead
    ],
    team_id: UUID,
    before_innings_number: int,
) -> int:

    return sum(
        card.total_runs

        for card
        in innings_cards

        if (
            card
            .batting_team
            .id
            == team_id

            and card
            .innings_number
            < before_innings_number
        )
    )


def chase_metrics(
    *,
    match: Match,
    innings_cards: list[
        InningsScorecardRead
    ],
    current: (
        InningsScorecardRead
        | None
    ),
) -> ChaseRead:

    if current is None:

        return ChaseRead(
            target=None,

            runs_required=None,

            balls_remaining=None,

            required_run_rate=None,
        )

    final_innings_number = (
        match.innings_per_team
        * 2
    )

    if (
        current.innings_number
        < final_innings_number
    ):

        return ChaseRead(
            target=None,

            runs_required=None,

            balls_remaining=None,

            required_run_rate=None,
        )

    batting_previous = (
        team_prior_runs(
            innings_cards=(
                innings_cards
            ),

            team_id=(
                current
                .batting_team
                .id
            ),

            before_innings_number=(
                current
                .innings_number
            ),
        )
    )

    bowling_total = (
        team_prior_runs(
            innings_cards=(
                innings_cards
            ),

            team_id=(
                current
                .bowling_team
                .id
            ),

            before_innings_number=(
                current
                .innings_number
                + 1
            ),
        )
    )

    target = (
        bowling_total
        - batting_previous
        + 1
    )

    runs_required = max(
        target
        - current.total_runs,
        0,
    )

    balls_remaining = None

    if (
        match.total_overs
        is not None
    ):

        balls_remaining = max(
            (
                match.total_overs
                * match.balls_per_over

                - current
                .legal_balls
            ),
            0,
        )

    return ChaseRead(
        target=target,

        runs_required=(
            runs_required
        ),

        balls_remaining=(
            balls_remaining
        ),

        required_run_rate=(
            required_run_rate(
                runs_required,
                balls_remaining,
                match.balls_per_over,
            )
        ),
    )
