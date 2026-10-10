
from __future__ import annotations
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models.enums import WicketType


STRIKER_ONLY = frozenset({
    WicketType.BOWLED,
    WicketType.CAUGHT,
    WicketType.LBW,
    WicketType.STUMPED,
    WicketType.HIT_WICKET,
})

NO_FIELDER = frozenset({
    WicketType.BOWLED,
    WicketType.LBW,
    WicketType.HIT_WICKET,
    WicketType.OBSTRUCTING_FIELD,
})

REQUIRES_FIELDER = frozenset({
    WicketType.CAUGHT,
    WicketType.STUMPED,
    WicketType.RUN_OUT,
})

NO_BALL_DISMISSALS = frozenset({
    WicketType.RUN_OUT,
    WicketType.OBSTRUCTING_FIELD,
})

WIDE_DISMISSALS = frozenset({
    WicketType.RUN_OUT,
    WicketType.STUMPED,
    WicketType.HIT_WICKET,
    WicketType.OBSTRUCTING_FIELD,
})


def resolve_dismissed_player(
    *,
    wicket_type: WicketType,
    striker_id: UUID,
    non_striker_id: UUID,
    requested_player_id: UUID | None,
) -> UUID:
    """
    Derive striker-only dismissals automatically.

    Run-out and obstructing-field dismissals
    require explicit identification where the
    current event lacks enough information.
    """
    if wicket_type in STRIKER_ONLY:
        if requested_player_id is not None and requested_player_id != striker_id:
            raise ValidationError(
                f"{wicket_type.value} can dismiss only the current striker.")

        return striker_id

    if requested_player_id is None:
        raise ValidationError(
            "Identify the dismissed batter for run out or obstructing the field.")

    if requested_player_id not in {striker_id, non_striker_id}:
        raise ValidationError(
            "Dismissed player must be one of the current batters.")

    return requested_player_id


def validate_fielder(
    *,
    wicket_type: WicketType,
    fielder_id: UUID | None,
    bowling_xi_ids: set[UUID],
) -> None:
    if wicket_type in NO_FIELDER:
        if fielder_id is not None:
            raise ValidationError(
                f"{wicket_type.value} must not have a fielder.")
        return

    if wicket_type in REQUIRES_FIELDER:
        if fielder_id is None:
            raise ValidationError(
                f"{wicket_type.value} requires a fielder.")

        if fielder_id not in bowling_xi_ids:
            raise ValidationError("Fielder must belong to the bowling team's playing XI.")


def validate_wicket_delivery(
    *,
    wicket_type: WicketType,
    no_ball: bool,
    wide_runs: int,
    running_runs: int,
    wicket_end: str | None,
) -> None:
    if (
        no_ball
        and wicket_type not in NO_BALL_DISMISSALS
    ):
        raise ValidationError(f"{wicket_type.value} is not permitted on a no-ball.")

    if wide_runs > 0 and wicket_type not in WIDE_DISMISSALS:
        raise ValidationError(
            f"{wicket_type.value} is not permitted on a wide.")

    if (
        running_runs > 0
        and wicket_type not in {
            WicketType.RUN_OUT,
            WicketType.OBSTRUCTING_FIELD,
        }
    ):
        raise ValidationError("Completed running runs are not supported with this dismissal.")

    if wicket_type == WicketType.RUN_OUT:
        if wicket_end not in {"striker_end", "non_striker_end"}:
            raise ValidationError("Run out requires the wicket end.")
        
    elif wicket_end is not None:
        raise ValidationError("wicket_end is only supported for run out.")
