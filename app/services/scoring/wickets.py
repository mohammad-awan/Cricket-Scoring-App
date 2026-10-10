from __future__ import annotations
from app.core.exceptions import ValidationError
from app.models import Innings, Match
from app.models.enums import WicketType
from app.repositories.scoring import ScoringRepository
from app.schemas.scoring import WicketCreate
from app.services.scoring.calculations import max_wickets
from app.services.scoring.types import DeliveryComponents, DerivedState


async def validate_wicket(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
    before: DerivedState,
    components: DeliveryComponents,
    wicket: WicketCreate,
) -> None:
    """
    Central Stage 5 dismissal
    validation.

    Nothing is written before all
    validations pass.
    """

    current_batters = {
        before.striker_id,
        before.non_striker_id,
    }

    if (
        wicket.dismissed_player_id
        not in current_batters
    ):

        raise ValidationError(
            "Dismissed player must "
            "be one of the two "
            "current batters"
        )

    striker_only = {
        WicketType.BOWLED,
        WicketType.CAUGHT,
        WicketType.LBW,
        WicketType.STUMPED,
        WicketType.HIT_WICKET,
    }

    if (
        wicket.wicket_type
        in striker_only

        and wicket
        .dismissed_player_id
        != before.striker_id
    ):

        raise ValidationError(
            f"{wicket.wicket_type.value} "
            "can dismiss only "
            "the striker"
        )

    # On a no-ball ordinary striker
    # dismissals do not apply.
    if (
        components.no_ball_runs
    ):

        allowed = {
            WicketType.RUN_OUT,
            WicketType.OBSTRUCTING_FIELD,
        }

        if (
            wicket.wicket_type
            not in allowed
        ):

            raise ValidationError(
                "On a no-ball this "
                "wicket type is not "
                "a valid dismissal"
            )

    # Wides allow only applicable
    # non-standard dismissals.
    if (
        components.wide_runs
    ):

        allowed = {
            WicketType.RUN_OUT,
            WicketType.STUMPED,
            WicketType.HIT_WICKET,
            WicketType.OBSTRUCTING_FIELD,
        }

        if (
            wicket.wicket_type
            not in allowed
        ):

            raise ValidationError(
                "This wicket type "
                "is not valid "
                "on a wide"
            )

    # Completed runs with an ordinary
    # bowled/caught/LBW/etc event are
    # invalid for this Stage 5 model.
    if (
        components.running_runs > 0

        and wicket.wicket_type
        not in {
            WicketType.RUN_OUT,
            WicketType.OBSTRUCTING_FIELD,
        }
    ):

        raise ValidationError(
            "Runs on a wicket "
            "delivery are supported "
            "only for run out or "
            "obstructing the field"
        )

    dismissed_before = (
        await repository
        .dismissed_player_ids(
            innings.id
        )
    )

    if (
        wicket.dismissed_player_id
        in dismissed_before
    ):

        raise ValidationError(
            "This batter has "
            "already been dismissed"
        )

    dismissed_belongs = (
        await repository
        .is_playing_team_player(
            match_id=match.id,

            team_id=(
                innings
                .batting_team_id
            ),

            player_id=(
                wicket
                .dismissed_player_id
            ),
        )
    )

    if not dismissed_belongs:

        raise ValidationError(
            "Dismissed player must "
            "belong to the batting "
            "playing XI"
        )

    if (
        wicket.fielder_id
        is not None
    ):

        fielder_belongs = (
            await repository
            .is_playing_team_player(
                match_id=match.id,

                team_id=(
                    innings
                    .bowling_team_id
                ),

                player_id=(
                    wicket
                    .fielder_id
                ),
            )
        )

        if not fielder_belongs:

            raise ValidationError(
                "Fielder must belong "
                "to the bowling "
                "playing XI"
            )

    wickets_after = (
        before.wickets
        + 1
    )

    all_out_after = (
        wickets_after
        >= max_wickets(
            match.players_per_side
        )
    )

    # Last wicket.
    if all_out_after:

        if (
            wicket.next_batter_id
            is not None
        ):

            raise ValidationError(
                "No next batter is "
                "allowed after the "
                "final wicket"
            )

        return

    if (
        wicket.next_batter_id
        is None
    ):

        raise ValidationError(
            "Select the next batter "
            "for this wicket"
        )

    if (
        wicket.next_batter_id
        in {
            before.striker_id,
            before.non_striker_id,
            wicket.dismissed_player_id,
        }
    ):

        raise ValidationError(
            "Next batter must be "
            "a different available "
            "batter"
        )

    if (
        wicket.next_batter_id
        in dismissed_before
    ):

        raise ValidationError(
            "Next batter has already "
            "been dismissed"
        )

    next_batter_belongs = (
        await repository
        .is_playing_team_player(
            match_id=match.id,

            team_id=(
                innings
                .batting_team_id
            ),

            player_id=(
                wicket
                .next_batter_id
            ),
        )
    )

    if not next_batter_belongs:

        raise ValidationError(
            "Next batter must belong "
            "to the batting "
            "playing XI"
        )
