from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Sequence
from app.repositories.scorecard import DeliveryScoreRow, RetirementScoreRow


@dataclass(
    frozen=True
)
class InningsTotals:

    runs: int

    wickets: int

    legal_balls: int


def innings_totals(
    deliveries: list[
        DeliveryScoreRow
    ],
    retirements: Sequence[
        RetirementScoreRow
    ] = (),
) -> InningsTotals:

    return InningsTotals(
        runs=sum(
            item.total_runs

            for item
            in deliveries
        ),

        wickets=sum(
            1

            for item
            in deliveries

            if (
                item
                .dismissed_player_id
                is not None
            )
        )
        # Retired out is a dismissal.
        + sum(
            1

            for item
            in retirements

            if item.retirement_type
            == "retired_out"
        ),

        legal_balls=sum(
            1

            for item
            in deliveries

            if item.is_legal_ball
        ),
    )
