from __future__ import annotations
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models.enums import RetirementType


class RetirementEvent(Protocol):
    player_id: UUID
    retirement_type: RetirementType


@dataclass(frozen=True)
class RetirementStatus:
    # Retired out is a dismissal (MCC Law 25.4.3).
    retired_out_ids: frozenset[UUID]
    # Retired hurt and not yet resumed (Law 25.4.2).
    retired_hurt_ids: frozenset[UUID]


def retirement_status(
    retirements: Iterable[RetirementEvent],
    *,
    crease_ids: set[UUID],
    dismissed_ids: set[UUID],
) -> RetirementStatus:
    """
    Classify batters from official retirements.

    A retired-hurt batter who has since resumed is
    either at the crease, dismissed, or retired again,
    so set arithmetic is enough; event order is not
    needed.
    """

    events = list(retirements)

    retired_out = frozenset(
        event.player_id
        for event in events
        if event.retirement_type == RetirementType.OUT
    )

    retired_hurt = frozenset(
        event.player_id
        for event in events
        if event.retirement_type == RetirementType.HURT
    ) - crease_ids - dismissed_ids - retired_out

    return RetirementStatus(
        retired_out_ids=retired_out,
        retired_hurt_ids=retired_hurt,
    )


def validate_retiring_player(
    player_id: UUID,
    *,
    striker_id: UUID,
    non_striker_id: UUID,
) -> None:
    if player_id not in {striker_id, non_striker_id}:
        raise ValidationError("Only a batter currently at the crease can retire.")


def crease_after_retirement(
    *,
    striker_id: UUID,
    non_striker_id: UUID,
    retiring_player_id: UUID,
    replacement_player_id: UUID | None,
) -> tuple[UUID, UUID]:
    """
    The incoming batter takes the retiring batter's end.

    With no replacement (retired out as the final
    wicket) the retiring batter's ID is kept, matching
    how the final dismissal is represented.
    """

    incoming = replacement_player_id or retiring_player_id

    if retiring_player_id == striker_id:
        return incoming, non_striker_id

    return striker_id, incoming
