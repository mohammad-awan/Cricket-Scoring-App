from __future__ import annotations
from uuid import UUID
from app.repositories.scorecard import DeliveryScoreRow
from app.schemas.match_setup import PlayerSummary
from app.schemas.scorecard import PartnershipRead
from app.services.scorecard.formatters import player_summary


def partnership_scorecard(
    deliveries: list[
        DeliveryScoreRow
    ],
) -> list[
    PartnershipRead
]:

    if not deliveries:

        return []

    result: list[
        PartnershipRead
    ] = []

    current_pair: (
        frozenset[UUID]
        | None
    ) = None

    current_players: dict[
        UUID,
        PlayerSummary,
    ] = {}

    current_runs = 0

    current_balls = 0

    partnership_number = 0

    wicket_number = 0

    def flush(
        ended_by_wicket: bool,
    ) -> None:

        nonlocal current_pair

        nonlocal current_players

        nonlocal current_runs

        nonlocal current_balls

        nonlocal partnership_number

        nonlocal wicket_number

        if (
            current_pair is None

            or len(
                current_players
            ) != 2
        ):

            return

        partnership_number += 1

        if ended_by_wicket:

            wicket_number += 1

            ended_at = (
                wicket_number
            )

        else:

            ended_at = None

        players = sorted(
            current_players
            .values(),

            key=lambda player: (
                str(
                    player.id
                )
            ),
        )

        result.append(
            PartnershipRead(
                number=(
                    partnership_number
                ),

                wicket_number=(
                    ended_at
                ),

                batter_one=(
                    players[0]
                ),

                batter_two=(
                    players[1]
                ),

                runs=(
                    current_runs
                ),

                legal_balls=(
                    current_balls
                ),
            )
        )

        current_pair = None

        current_players = {}

        current_runs = 0

        current_balls = 0

    for item in deliveries:

        pair = frozenset(
            {
                item.striker_id,
                item.non_striker_id,
            }
        )

        if (
            current_pair
            is not None

            and pair
            != current_pair
        ):

            flush(
                False
            )

        if (
            current_pair
            is None
        ):

            current_pair = pair

            current_players = {
                item.striker_id:
                    player_summary(
                        item.striker_id,
                        item.striker_name,
                        item.striker_short_name,
                    ),

                item.non_striker_id:
                    player_summary(
                        item.non_striker_id,
                        item.non_striker_name,
                        item.non_striker_short_name,
                    ),
            }

        current_runs += (
            item.total_runs
        )

        if item.is_legal_ball:

            current_balls += 1

        if (
            item
            .dismissed_player_id
            is not None
        ):

            flush(
                True
            )

    flush(
        False
    )

    return result
