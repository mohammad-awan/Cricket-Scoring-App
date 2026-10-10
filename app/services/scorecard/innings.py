from __future__ import annotations
from dataclasses import dataclass
from app.repositories.scorecard import DeliveryScoreRow


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
        ),

        legal_balls=sum(
            1

            for item
            in deliveries

            if item.is_legal_ball
        ),
    )
