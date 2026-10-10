from __future__ import annotations
from app.repositories.scorecard import DeliveryScoreRow
from app.schemas.scorecard import ExtrasRead


def extras_summary(
    deliveries: list[
        DeliveryScoreRow
    ],
) -> ExtrasRead:

    wides = sum(
        item.wide_runs

        for item
        in deliveries
    )

    no_balls = sum(
        item.no_ball_runs

        for item
        in deliveries
    )

    byes = sum(
        item.bye_runs

        for item
        in deliveries
    )

    leg_byes = sum(
        item.leg_bye_runs

        for item
        in deliveries
    )

    return ExtrasRead(
        total=(
            wides
            + no_balls
            + byes
            + leg_byes
        ),

        wides=wides,

        no_balls=no_balls,

        byes=byes,

        leg_byes=leg_byes,
    )
