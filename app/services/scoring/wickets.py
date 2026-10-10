from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from app.core.exceptions import ValidationError
from app.domain.batting_order import select_next_batter, validate_batting_order
from app.domain.retirements import retirement_status
from app.domain.wickets import (
    resolve_dismissed_player,
    validate_fielder,
    validate_wicket_delivery,
)
from app.models import Innings, Match
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import WicketCreate
from app.services.scoring.calculations import max_wickets
from app.services.scoring.types import DeliveryComponents, DerivedState


@dataclass(frozen=True)
class ResolvedWicket:
    dismissed_player_id: UUID
    next_batter_id: UUID | None


async def validate_wicket(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
    before: DerivedState,
    components: DeliveryComponents,
    wicket: WicketCreate,
) -> ResolvedWicket:
    """
    Validate wicket and resolve authoritative
    participant IDs.

    Must run inside the delivery transaction,
    after locking the innings.
    """

    dismissed_id = resolve_dismissed_player(
        wicket_type=wicket.wicket_type,
        striker_id=before.striker_id,
        non_striker_id=before.non_striker_id,
        requested_player_id=wicket.dismissed_player_id,
    )

    validate_wicket_delivery(
        wicket_type=wicket.wicket_type,
        no_ball=components.no_ball_runs > 0,
        wide_runs=components.wide_runs,
        running_runs=components.running_runs,
        wicket_end=wicket.wicket_end,
    )

    selections = await repository.get_playing_xi(match.id, innings.batting_team_id)
    ordered_ids = validate_batting_order(selections, players_per_side=match.players_per_side)

    if dismissed_id not in ordered_ids:
        raise ValidationError("Dismissed player does not belong to the batting XI.")

    bowling_selections = await repository.get_playing_xi(match.id, innings.bowling_team_id)
    bowling_ids = {selection.player_id for selection in bowling_selections}

    validate_fielder(
        wicket_type=wicket.wicket_type,
        fielder_id=wicket.fielder_id,
        bowling_xi_ids=bowling_ids,
    )

    dismissed_by_delivery = await repository.dismissed_player_ids(innings.id)
    retired = retirement_status(
        await repository.get_official_retirements(innings.id),
        crease_ids={before.striker_id, before.non_striker_id},
        dismissed_ids=dismissed_by_delivery,
    )
    dismissed_before = dismissed_by_delivery | retired.retired_out_ids

    if dismissed_id in dismissed_before:
        raise ValidationError("This player has already been dismissed.")

    if before.striker_id == before.non_striker_id:
        raise ValidationError("Striker and non-striker cannot be the same player.")

    wickets_after = before.wickets + 1

    if wickets_after > max_wickets(match.players_per_side):
        raise ValidationError("Maximum wickets already reached.")

    final_wicket = wickets_after >= max_wickets(match.players_per_side)

    next_batter_id = select_next_batter(
        ordered_ids,
        striker_id=before.striker_id,
        non_striker_id=before.non_striker_id,
        dismissed_player_ids=dismissed_before,
        dismissed_player_id=dismissed_id,
        selection_mode=wicket.selection_mode,
        manual_player_id=wicket.next_batter_id,
        final_wicket=final_wicket,
        resumable_player_ids=set(retired.retired_hurt_ids),
    )

    return ResolvedWicket(dismissed_player_id=dismissed_id, next_batter_id=next_batter_id)
