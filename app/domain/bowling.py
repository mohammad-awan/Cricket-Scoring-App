
from __future__ import annotations
from collections.abc import Iterable
from math import ceil
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models import Delivery, Match
from app.models.enums import MatchType


def bowler_ball_quota(match: Match) -> int | None:
    """
    Maximum legal deliveries allowed per bowler.

    T20/ODI: up to one fifth of the innings
    overs, rounded up when not divisible by 5.

    Other limited-overs formats: same policy.
    Test matches: no limited-overs quota.
    """
    if match.match_type == MatchType.TEST:
        return None

    if match.total_overs is None:
        return None

    overs_per_bowler = ceil(match.total_overs / 5)
    return overs_per_bowler * match.balls_per_over


def legal_balls_by_bowler(deliveries: Iterable[Delivery], bowler_id: UUID) -> int:
    return sum(
        1
        for delivery in deliveries
        if (
            delivery.bowler_id == bowler_id
            and delivery.is_legal_ball
        )
    )


def validate_bowler_quota(
    *,
    match: Match,
    deliveries: list[Delivery],
    bowler_id: UUID,
    starting_new_over: bool = False,
) -> None:
    quota = bowler_ball_quota(match)

    if quota is None:
        return

    used = legal_balls_by_bowler(deliveries, bowler_id)

    if used >= quota:
        raise ValidationError(
            "Bowler has reached the "
            "maximum legal-ball quota."
        )

    if (
        starting_new_over
        and used + match.balls_per_over > quota
    ):
        raise ValidationError(
            "This bowler does not have enough "
            "remaining quota for a full over."
        )
