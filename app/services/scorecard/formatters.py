from __future__ import annotations
from uuid import UUID
from app.schemas.match_setup import PlayerSummary


def overs_display(
    legal_balls: int,
    balls_per_over: int,
) -> str:

    completed, balls = divmod(
        legal_balls,
        balls_per_over,
    )

    return (
        f"{completed}."
        f"{balls}"
    )


def run_rate(
    runs: int,
    legal_balls: int,
    balls_per_over: int,
) -> float:

    if legal_balls <= 0:

        return 0.0

    overs = (
        legal_balls
        / balls_per_over
    )

    return round(
        runs
        / overs,
        2,
    )


def strike_rate(
    runs: int,
    balls: int,
) -> float:

    if balls <= 0:

        return 0.0

    return round(
        (
            runs
            * 100
        )
        / balls,
        2,
    )


def economy_rate(
    runs: int,
    legal_balls: int,
    balls_per_over: int,
) -> float:

    if legal_balls <= 0:

        return 0.0

    overs = (
        legal_balls
        / balls_per_over
    )

    return round(
        runs
        / overs,
        2,
    )


def required_run_rate(
    runs_required: (
        int | None
    ),
    balls_remaining: (
        int | None
    ),
    balls_per_over: int,
) -> float | None:

    if (
        runs_required is None
        or balls_remaining is None
    ):

        return None

    if runs_required <= 0:

        return 0.0

    if balls_remaining <= 0:

        return None

    overs_remaining = (
        balls_remaining
        / balls_per_over
    )

    return round(
        runs_required
        / overs_remaining,
        2,
    )


def player_summary(
    player_id: UUID,
    full_name: str,
    short_name: (
        str | None
    ),
) -> PlayerSummary:

    return PlayerSummary(
        id=player_id,

        full_name=(
            full_name
        ),

        short_name=(
            short_name
        ),
    )
