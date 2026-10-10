from __future__ import annotations
from collections import defaultdict
from uuid import UUID
from app.repositories.scorecard import DeliveryScoreRow
from app.schemas.scorecard import BowlingScorecardRow
from app.services.scorecard.formatters import economy_rate, overs_display, player_summary


BOWLER_WICKET_TYPES = {
    "bowled",
    "caught",
    "lbw",
    "stumped",
    "hit_wicket",
}


def bowling_scorecard(
    *,
    deliveries: list[
        DeliveryScoreRow
    ],
    balls_per_over: int,
) -> list[
    BowlingScorecardRow
]:

    names: dict[
        UUID,
        tuple[
            str,
            str | None,
        ],
    ] = {}

    legal_balls: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    runs_conceded: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    wickets: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    wides: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    no_balls: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    over_legal: dict[
        tuple[
            UUID,
            int,
        ],
        int,
    ] = defaultdict(
        int
    )

    over_runs: dict[
        tuple[
            UUID,
            int,
        ],
        int,
    ] = defaultdict(
        int
    )

    for item in deliveries:

        names[
            item.bowler_id
        ] = (
            item.bowler_name,
            item.bowler_short_name,
        )

        if item.is_legal_ball:

            legal_balls[
                item.bowler_id
            ] += 1

            over_legal[
                (
                    item.bowler_id,
                    item.over_number,
                )
            ] += 1

        # Byes and leg byes are
        # not charged to bowler.
        conceded = (
            item.batter_runs
            + item.wide_runs
            + item.no_ball_runs
        )

        runs_conceded[
            item.bowler_id
        ] += conceded

        over_runs[
            (
                item.bowler_id,
                item.over_number,
            )
        ] += conceded

        wides[
            item.bowler_id
        ] += (
            item.wide_runs
        )

        no_balls[
            item.bowler_id
        ] += (
            item.no_ball_runs
        )

        if (
            item.wicket_type
            in BOWLER_WICKET_TYPES
        ):

            wickets[
                item.bowler_id
            ] += 1

    maidens: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    for (
        key,
        legal_count,
    ) in over_legal.items():

        bowler_id, _ = key

        if (
            legal_count
            == balls_per_over

            and over_runs[
                key
            ] == 0
        ):

            maidens[
                bowler_id
            ] += 1

    result: list[
        BowlingScorecardRow
    ] = []

    for (
        bowler_id,
        (
            full_name,
            short_name,
        ),
    ) in names.items():

        bowler_balls = (
            legal_balls[
                bowler_id
            ]
        )

        bowler_runs = (
            runs_conceded[
                bowler_id
            ]
        )

        result.append(
            BowlingScorecardRow(
                player=(
                    player_summary(
                        bowler_id,
                        full_name,
                        short_name,
                    )
                ),

                overs=(
                    overs_display(
                        bowler_balls,
                        balls_per_over,
                    )
                ),

                legal_balls=(
                    bowler_balls
                ),

                maidens=(
                    maidens[
                        bowler_id
                    ]
                ),

                runs_conceded=(
                    bowler_runs
                ),

                wickets=(
                    wickets[
                        bowler_id
                    ]
                ),

                wides=(
                    wides[
                        bowler_id
                    ]
                ),

                no_balls=(
                    no_balls[
                        bowler_id
                    ]
                ),

                economy=(
                    economy_rate(
                        bowler_runs,
                        bowler_balls,
                        balls_per_over,
                    )
                ),
            )
        )

    result.sort(
        key=lambda row: (
            -row.legal_balls,
            row.player.full_name,
        )
    )

    return result
