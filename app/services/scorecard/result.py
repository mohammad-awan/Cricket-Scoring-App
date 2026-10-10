from __future__ import annotations
from app.models import Innings, Match
from app.models.enums import MatchStatus


def result_summary(
    match: Match,
) -> str | None:

    if (
        match.result_type
        is None
    ):

        return None

    if (
        match.result_type
        == "tie"
    ):

        return "Match tied"

    winner = (
        match.winner_team
    )

    if winner is None:

        return None

    margin = (
        match.result_margin
        or 0
    )

    if (
        match.result_type
        == "runs"
    ):

        unit = (
            "run"
            if margin == 1
            else "runs"
        )

    else:

        unit = (
            "wicket"
            if margin == 1
            else "wickets"
        )

    return (
        f"{winner.name} "
        f"won by "
        f"{margin} "
        f"{unit}"
    )


def state_label(
    match: Match,
    innings: (
        Innings | None
    ),
) -> str:

    if (
        match.status
        == MatchStatus.DRAFT
    ):

        return "Draft"

    if (
        match.status
        == MatchStatus.READY
    ):

        return "Ready"

    if (
        match.status
        == MatchStatus.INNINGS_BREAK
    ):

        return (
            "Innings Break"
        )

    if (
        match.status
        == MatchStatus.COMPLETED
    ):

        return "Completed"

    if (
        match.status
        == MatchStatus.ABANDONED
    ):

        return "Abandoned"

    if innings is None:

        return "Live"

    return (
        f"Innings "
        f"{innings.innings_number} "
        f"Live"
    )
