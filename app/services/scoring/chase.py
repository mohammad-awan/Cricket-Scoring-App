from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models import Innings, Match
from app.models.enums import InningsStatus, MatchStatus
from app.services.scoring.calculations import overs_complete, max_innings, max_wickets
from app.services.scoring.types import ChaseState
from app.domain.playing_side import batting_side_size


def chase_target(
    *,
    opponent_runs: int,
    batting_previous_runs: int,
) -> int:

    return (
        opponent_runs
        - batting_previous_runs
        + 1
    )


def result_summary(
    *,
    batting_team_name: str,
    bowling_team_name: str,
    batting_runs: int,
    bowling_runs: int,
    wickets: int,
    players_per_side: int,
) -> str:

    if batting_runs > bowling_runs:

        margin = max(
            players_per_side
            - 1
            - wickets,
            1,
        )

        unit = (
            "wicket"
            if margin == 1
            else "wickets"
        )

        return (
            f"{batting_team_name} "
            f"won by "
            f"{margin} "
            f"{unit}"
        )

    if (
        batting_runs
        == bowling_runs
    ):

        return "Match tied"

    margin = (
        bowling_runs
        - batting_runs
    )

    unit = (
        "run"
        if margin == 1
        else "runs"
    )

    return (
        f"{bowling_team_name} "
        f"won by "
        f"{margin} "
        f"{unit}"
    )


def team_runs(
    innings_list: list[
        Innings
    ],
    totals: dict[
        UUID,
        tuple[
            int,
            int,
            int,
        ],
    ],
    team_id: UUID,
    *,
    exclude_innings_id: (
        UUID | None
    ) = None,
) -> int:

    return sum(
        totals.get(
            item.id,
            (
                0,
                0,
                0,
            ),
        )[0]

        for item
        in innings_list

        if (
            item.batting_team_id
            == team_id

            and item.id
            != exclude_innings_id
        )
    )


def chase_state(
    match: Match,
    innings: Innings,
    innings_list: list[
        Innings
    ],
    totals: dict[
        UUID,
        tuple[
            int,
            int,
            int,
        ],
    ],
) -> ChaseState | None:

    if (
        innings.innings_number
        < max_innings(
            match.innings_per_team
        )
    ):

        return None

    batting_previous = (
        team_runs(
            innings_list,
            totals,
            innings.batting_team_id,
            exclude_innings_id=(
                innings.id
            ),
        )
    )

    bowling_runs = (
        team_runs(
            innings_list,
            totals,
            innings.bowling_team_id,
        )
    )

    current_runs = (
        totals.get(
            innings.id,
            (
                0,
                0,
                0,
            ),
        )[0]
    )

    return ChaseState(
        target=chase_target(
            opponent_runs=(
                bowling_runs
            ),

            batting_previous_runs=(
                batting_previous
            ),
        ),

        batting_runs=(
            batting_previous
            + current_runs
        ),

        bowling_runs=(
            bowling_runs
        ),
    )


def innings_finished(
    match: Match,
    innings: Innings,
    legal_balls: int,
    wickets: int,
    chase: (
        ChaseState | None
    ),
) -> bool:

    if (
        innings.status
        == InningsStatus.COMPLETED
    ):
        return True

    if (
        wickets
        >= max_wickets(
            batting_side_size(match, innings)
        )
    ):
        return True

    if overs_complete(
        match,
        legal_balls,
    ):
        return True

    return (
        chase is not None
        and chase.batting_runs
        > chase.bowling_runs
    )


def clear_match_result(
    match: Match,
) -> None:

    match.winner_team_id = (
        None
    )

    match.result_type = (
        None
    )

    match.result_margin = (
        None
    )

    match.completed_at = (
        None
    )


def finalize_match_result(
    match: Match,
    innings: Innings,
    *,
    wickets: int,
    chase: ChaseState,
) -> None:

    if (
        chase.batting_runs
        > chase.bowling_runs
    ):

        match.winner_team_id = (
            innings
            .batting_team_id
        )

        match.result_type = (
            "wickets"
        )

        match.result_margin = max(
            (
                batting_side_size(match, innings)
                - 1
                - wickets
            ),
            1,
        )

    elif (
        chase.batting_runs
        == chase.bowling_runs
    ):

        match.winner_team_id = (
            None
        )

        match.result_type = (
            "tie"
        )

        match.result_margin = (
            0
        )

    else:

        match.winner_team_id = (
            innings
            .bowling_team_id
        )

        match.result_type = (
            "runs"
        )

        match.result_margin = (
            chase.bowling_runs
            - chase.batting_runs
        )

    match.completed_at = (
        datetime.now(
            timezone.utc
        )
    )


def close_innings(
    match: Match,
    innings: Innings,
    *,
    wickets: int,
    chase: (
        ChaseState | None
    ),
) -> None:

    innings.status = (
        InningsStatus.COMPLETED
    )

    if (
        innings.innings_number
        >= max_innings(
            match.innings_per_team
        )
    ):

        if chase is None:

            raise ValidationError(
                "Final innings result "
                "could not be derived"
            )

        match.status = (
            MatchStatus.COMPLETED
        )

        finalize_match_result(
            match,
            innings,
            wickets=wickets,
            chase=chase,
        )

    else:

        match.status = (
            MatchStatus.INNINGS_BREAK
        )

        clear_match_result(
            match
        )
