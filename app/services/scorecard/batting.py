from __future__ import annotations
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID
from app.repositories.scorecard import DeliveryScoreRow, MatchPlayerRow, RetirementScoreRow
from app.schemas.scorecard import BattingScorecardRow
from app.services.scorecard.formatters import player_summary, strike_rate


def dismissal_text(
    delivery: DeliveryScoreRow,
) -> str:

    wicket_type = (
        delivery
        .wicket_type
    )

    if wicket_type == "bowled":

        return (
            "b "
            f"{delivery.bowler_name}"
        )

    if wicket_type == "caught":

        fielder = (
            delivery
            .fielder_name

            or "fielder"
        )

        return (
            f"c {fielder} "
            f"b "
            f"{delivery.bowler_name}"
        )

    if wicket_type == "lbw":

        return (
            "lbw b "
            f"{delivery.bowler_name}"
        )

    if wicket_type == "run_out":

        if (
            delivery
            .fielder_name
        ):

            return (
                "run out "
                f"("
                f"{delivery.fielder_name}"
                f")"
            )

        return "run out"

    if wicket_type == "stumped":

        fielder = (
            delivery
            .fielder_name

            or "wicketkeeper"
        )

        return (
            f"st {fielder} "
            f"b "
            f"{delivery.bowler_name}"
        )

    if wicket_type == "hit_wicket":

        return (
            "hit wicket "
            f"b "
            f"{delivery.bowler_name}"
        )

    if (
        wicket_type
        == "obstructing_field"
    ):

        return (
            "obstructing the field"
        )

    return "out"


def retirement_labels(
    deliveries: Sequence[
        DeliveryScoreRow
    ],
    retirements: Sequence[
        RetirementScoreRow
    ],
) -> dict[UUID, str]:
    """
    "retired out" or "retired hurt" for batters whose
    latest retirement still stands. A retired-hurt
    batter who resumed is labelled by what happened
    afterwards instead.
    """

    latest: dict[UUID, RetirementScoreRow] = {}

    for item in retirements:
        latest[item.player_id] = item

    labels: dict[UUID, str] = {}

    for player_id, item in latest.items():

        if item.retirement_type == "retired_out":
            labels[player_id] = "retired out"
            continue

        resumed = any(
            delivery.delivery_number > item.after_delivery_number
            and player_id in {
                delivery.striker_id,
                delivery.non_striker_id,
                delivery.next_batter_id,
            }
            for delivery in deliveries
        ) or any(
            later.event_number > item.event_number
            and later.replacement_player_id == player_id
            for later in retirements
        )

        if not resumed:
            labels[player_id] = "retired hurt"

    return labels


def batting_scorecard(
    *,
    players: list[
        MatchPlayerRow
    ],
    deliveries: list[
        DeliveryScoreRow
    ],
    retirements: Sequence[
        RetirementScoreRow
    ] = (),
) -> list[
    BattingScorecardRow
]:

    runs: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    balls: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    fours: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    sixes: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    appeared: set[
        UUID
    ] = set()

    dismissals: dict[
        UUID,
        str,
    ] = {}

    for item in deliveries:

        appeared.add(
            item.striker_id
        )

        appeared.add(
            item.non_striker_id
        )

        runs[
            item.striker_id
        ] += (
            item.batter_runs
        )

        # Wide does not count as
        # a ball faced by batter.
        if (
            item.wide_runs
            == 0
        ):

            balls[
                item.striker_id
            ] += 1

        if (
            item.batter_runs
            == 4
        ):

            fours[
                item.striker_id
            ] += 1

        if (
            item.batter_runs
            == 6
        ):

            sixes[
                item.striker_id
            ] += 1

        if (
            item
            .dismissed_player_id
            is not None
        ):

            appeared.add(
                item
                .dismissed_player_id
            )

            dismissals[
                item
                .dismissed_player_id
            ] = (
                dismissal_text(
                    item
                )
            )

    for item in retirements:

        appeared.add(
            item.player_id
        )

        if (
            item.replacement_player_id
            is not None
        ):

            appeared.add(
                item.replacement_player_id
            )

    retired = retirement_labels(
        deliveries,
        retirements,
    )

    ordered = sorted(
        players,

        key=lambda player: (
            player.batting_order
            is None,

            player.batting_order
            or 999,

            player.full_name,
        ),
    )

    result: list[
        BattingScorecardRow
    ] = []

    for player in ordered:

        player_runs = (
            runs[
                player.player_id
            ]
        )

        player_balls = (
            balls[
                player.player_id
            ]
        )

        did_appear = (
            player.player_id
            in appeared
        )

        dismissal = (
            dismissals.get(
                player.player_id
            )
        )

        retirement = (
            retired.get(
                player.player_id
            )
        )

        if (
            dismissal
            is not None
        ):

            dismissal_label = (
                dismissal
            )

            is_not_out = False

        elif (
            retirement
            is not None
        ):

            dismissal_label = (
                retirement
            )

            # Retired hurt is recorded as not out;
            # retired out is a dismissal.
            is_not_out = (
                retirement
                == "retired hurt"
            )

        elif did_appear:

            dismissal_label = (
                "not out"
            )

            is_not_out = True

        else:

            dismissal_label = (
                "did not bat"
            )

            is_not_out = False

        result.append(
            BattingScorecardRow(
                player=(
                    player_summary(
                        player.player_id,
                        player.full_name,
                        player.short_name,
                    )
                ),

                batting_position=(
                    player
                    .batting_order
                ),

                dismissal=(
                    dismissal_label
                ),

                is_not_out=(
                    is_not_out
                ),

                runs=(
                    player_runs
                ),

                balls=(
                    player_balls
                ),

                fours=(
                    fours[
                        player
                        .player_id
                    ]
                ),

                sixes=(
                    sixes[
                        player
                        .player_id
                    ]
                ),

                strike_rate=(
                    strike_rate(
                        player_runs,
                        player_balls,
                    )
                ),
            )
        )

    return result
