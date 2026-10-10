from __future__ import annotations
from uuid import UUID
from app.core.exceptions import NotFoundError
from app.models import Delivery, Player
from app.repositories.scoring import ScoringRepository
from app.schemas.match_setup import PlayerSummary
from app.schemas.scoring import DeliveryRead


async def player_or_error(
    repository: ScoringRepository,
    player_id: UUID,
    label: str,
) -> Player:

    player = await repository.get_player(
        player_id
    )

    if player is None:

        raise NotFoundError(
            f"{label} not found"
        )

    return player


def player_summary(
    player: Player | None,
) -> PlayerSummary | None:

    if player is None:
        return None

    return (
        PlayerSummary
        .model_validate(
            player
        )
    )


def delivery_read(
    item: Delivery,
) -> DeliveryRead:

    corrections = list(
        getattr(
            item,
            "corrections",
            [],
        )
        or []
    )

    correction_reason = None

    if corrections:

        latest = max(
            corrections,
            key=lambda value:
                value.created_at,
        )

        correction_reason = (
            latest.reason
        )

    return DeliveryRead(
        id=item.id,

        sequence=(
            item.delivery_number
        ),

        over_number=(
            item.over_number
        ),

        ball_number=(
            item.ball_number
        ),

        striker=(
            PlayerSummary
            .model_validate(
                item.striker
            )
        ),

        non_striker=(
            PlayerSummary
            .model_validate(
                item.non_striker
            )
        ),

        bowler=(
            PlayerSummary
            .model_validate(
                item.bowler
            )
        ),

        batter_runs=(
            item.batter_runs
        ),

        extra_runs=(
            item.extra_runs
        ),

        wide_runs=(
            item.wide_runs
        ),

        no_ball_runs=(
            item.no_ball_runs
        ),

        bye_runs=(
            item.bye_runs
        ),

        leg_bye_runs=(
            item.leg_bye_runs
        ),

        total_runs=(
            item.total_runs
        ),

        is_legal_ball=(
            item.is_legal_ball
        ),

        wicket_type=(
            item.wicket_type
        ),

        dismissed_player=(
            player_summary(
                item.dismissed_player
            )
        ),

        fielder=(
            player_summary(
                item.fielder
            )
        ),

        next_batter=(
            player_summary(
                item.next_batter
            )
        ),

        status=(
            item.status
        ),

        correction_reason=(
            correction_reason
        ),

        recorded_at=(
            item.recorded_at
        ),
    )
