from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.retirements import RetirementStatus, retirement_status
from app.models import BatterRetirement, Delivery, Innings, Match
from app.models.enums import InningsStatus, MatchStatus, RetirementType
from app.repositories.scoring import ScoringRepository
from app.schemas.match_setup import PlayerSummary, TeamSummary
from app.schemas.retirements import RetirementRead
from app.schemas.scoring import InningsSummary, ScoringStateRead
from app.services.scoring.calculations import (
    delivery_running_runs,
    overs_complete,
    post_delivery_batters,
    ball_position,
    bowler_change_required,
    current_run_rate,
    max_innings,
    max_wickets,
    overs_display,
    overs_parts,
    previous_over_bowler_id,
)
from app.services.scoring.chase import chase_state, innings_finished, result_summary
from app.services.scoring.presenters import delivery_read, player_or_error
from app.services.scoring.types import DerivedState
from app.domain.playing_side import batting_side_size


def rebuild_from_deliveries(
    innings: Innings,
    deliveries: list[
        Delivery
    ],
    *,
    balls_per_over: int,
) -> DerivedState:
    """
    Official state is derived from
    non-void delivery history.
    """

    if not deliveries:

        if (
            innings.striker_id
            is None
            or innings.non_striker_id
            is None
        ):

            raise ValidationError(
                "Opening batters "
                "are not configured"
            )

        return DerivedState(
            total_runs=0,

            legal_balls=0,

            wickets=0,

            striker_id=(
                innings.striker_id
            ),

            non_striker_id=(
                innings.non_striker_id
            ),
        )

    total_runs = sum(
        int(
            item.total_runs
        )
        for item
        in deliveries
    )

    legal_balls = sum(
        1
        for item
        in deliveries
        if item.is_legal_ball
    )

    wickets = sum(
        1
        for item
        in deliveries
        if (
            getattr(
                item,
                "dismissed_player_id",
                None,
            )
            is not None
            or getattr(
                item,
                "wicket_type",
                None,
            )
            is not None
        )
    )

    last = (
        deliveries[-1]
    )

    (
        striker_id,
        non_striker_id,
    ) = post_delivery_batters(
        striker_id=(
            last.striker_id
        ),

        non_striker_id=(
            last.non_striker_id
        ),

        running_runs=(
            delivery_running_runs(
                last
            )
        ),

        is_legal_ball=(
            last.is_legal_ball
        ),

        legal_balls_after=(
            legal_balls
        ),

        balls_per_over=(
            balls_per_over
        ),

        dismissed_player_id=(
            getattr(
                last,
                "dismissed_player_id",
                None,
            )
        ),

        next_batter_id=(
            getattr(
                last,
                "next_batter_id",
                None,
            )
        ),

        wicket_end=(
            getattr(
                last,
                "wicket_end",
                None,
            )
        ),
    )

    return DerivedState(
        total_runs=(
            total_runs
        ),

        legal_balls=(
            legal_balls
        ),

        wickets=(
            wickets
        ),

        striker_id=(
            striker_id
        ),

        non_striker_id=(
            non_striker_id
        ),
    )


def trailing_retirements(
    deliveries: list[Delivery],
    retirements: list[BatterRetirement],
) -> list[BatterRetirement]:
    """
    Official retirements after the latest official
    delivery. Earlier ones are already reflected in
    the batters recorded on later deliveries.
    """

    anchor = deliveries[-1].delivery_number if deliveries else 0

    return [
        item
        for item in retirements
        if item.after_delivery_number >= anchor
    ]


def rebuild_innings_state(
    innings: Innings,
    deliveries: list[Delivery],
    retirements: list[BatterRetirement],
    *,
    balls_per_over: int,
) -> DerivedState:
    """
    Official state replayed from deliveries and
    retirements as one timeline.

    Retirements consume no ball and add no runs.
    Retired out counts as a wicket; retired hurt
    does not.
    """

    base = rebuild_from_deliveries(
        innings,
        deliveries,
        balls_per_over=balls_per_over,
    )

    retired_out = sum(
        1
        for item in retirements
        if item.retirement_type == RetirementType.OUT
    )

    striker_id = base.striker_id
    non_striker_id = base.non_striker_id

    trailing = trailing_retirements(deliveries, retirements)

    if trailing:
        striker_id = trailing[-1].striker_after_id
        non_striker_id = trailing[-1].non_striker_after_id

    return DerivedState(
        total_runs=base.total_runs,
        legal_balls=base.legal_balls,
        wickets=base.wickets + retired_out,
        striker_id=striker_id,
        non_striker_id=non_striker_id,
    )


def batter_status(
    deliveries: list[Delivery],
    retirements: list[BatterRetirement],
    derived: DerivedState,
) -> tuple[set[UUID], RetirementStatus]:
    """
    Returns (dismissed by delivery, retirement status).
    """

    dismissed = {
        item.dismissed_player_id
        for item in deliveries
        if item.dismissed_player_id is not None
    }

    status = retirement_status(
        retirements,
        crease_ids={derived.striker_id, derived.non_striker_id},
        dismissed_ids=dismissed,
    )

    return dismissed, status


async def load_innings_state(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
) -> tuple[list[Delivery], list[BatterRetirement], DerivedState]:
    deliveries = await repository.get_recorded_deliveries_plain(innings.id)
    retirements = await repository.get_official_retirements(innings.id)

    derived = rebuild_innings_state(
        innings,
        deliveries,
        retirements,
        balls_per_over=match.balls_per_over,
    )

    return deliveries, retirements, derived


def retirement_read(item: BatterRetirement) -> RetirementRead:
    return RetirementRead(
        id=item.id,
        event_number=item.event_number,
        after_delivery_number=item.after_delivery_number,
        player=PlayerSummary.model_validate(item.player),
        retirement_type=item.retirement_type,
        replacement_player=(
            PlayerSummary.model_validate(item.replacement_player)
            if item.replacement_player is not None
            else None
        ),
        selection_mode=item.selection_mode,
        reason=item.reason,
        status=item.status,
        created_at=item.created_at,
    )


def ensure_scoreable(
    match: Match,
    innings: Innings,
) -> None:

    if (
        match.status
        not in {
            MatchStatus.READY,
            MatchStatus.LIVE,
        }
    ):

        raise ConflictError(
            "Scoring is allowed "
            "only when the match "
            "is ready or live"
        )

    if (
        innings.status
        not in {
            InningsStatus.PENDING,
            InningsStatus.LIVE,
        }
    ):

        raise ConflictError(
            f"Innings "
            f"{innings.innings_number} "
            "is not available "
            "for scoring"
        )

    if (
        innings.striker_id
        is None
        or innings.non_striker_id
        is None
        or innings.current_bowler_id
        is None
    ):

        raise ValidationError(
            "Opening participants "
            "are incomplete"
        )


async def state_response(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
) -> ScoringStateRead:

    deliveries = (
        await repository
        .get_recorded_deliveries(
            innings.id
        )
    )

    retirements = (
        await repository
        .get_official_retirements(
            innings.id,
            with_players=True,
        )
    )

    derived = (
        rebuild_innings_state(
            innings,
            deliveries,
            retirements,
            balls_per_over=(
                match.balls_per_over
            ),
        )
    )

    (
        delivery_dismissed,
        retired,
    ) = batter_status(
        deliveries,
        retirements,
        derived,
    )

    striker = (
        await player_or_error(
            repository,
            derived.striker_id,
            "Striker",
        )
    )

    non_striker = (
        await player_or_error(
            repository,
            derived.non_striker_id,
            "Non-striker",
        )
    )

    if (
        innings.current_bowler_id
        is None
    ):

        raise ValidationError(
            "Current bowler "
            "is not configured"
        )

    bowler = (
        await player_or_error(
            repository,
            innings.current_bowler_id,
            "Current bowler",
        )
    )

    (
        completed_overs,
        balls_in_over,
    ) = overs_parts(
        derived.legal_balls,
        match.balls_per_over,
    )

    (
        next_over,
        next_ball,
    ) = ball_position(
        derived.legal_balls,
        match.balls_per_over,
    )

    next_sequence = (
        await repository
        .next_delivery_number(
            innings.id
        )
    )

    history = (
        await repository
        .get_delivery_history(
            innings.id,
            limit=20,
        )
    )

    dismissed_ids = sorted(
        delivery_dismissed
        | retired.retired_out_ids,
        key=str,
    )

    cache_matches_history = (
        innings.total_runs
        == derived.total_runs

        and innings.wickets
        == derived.wickets

        and innings.legal_balls
        == derived.legal_balls

        and innings.striker_id
        == derived.striker_id

        and innings.non_striker_id
        == derived.non_striker_id
    )

    innings_list = (
        await repository
        .list_innings(
            match.id
        )
    )

    totals = (
        await repository
        .delivery_totals(
            match.id
        )
    )

    chase = chase_state(
        match,
        innings,
        innings_list,
        totals,
    )

    innings_complete = (
        innings_finished(
            match,
            innings,
            derived.legal_balls,
            derived.wickets,
            chase,
        )
    )

    match_over = (
        match.status
        in {
            MatchStatus.COMPLETED,
            MatchStatus.ABANDONED,
        }
    )

    has_next_innings = (
        innings.innings_number
        < max_innings(
            match.innings_per_team
        )
    )

    can_start_next_innings = (
        innings_complete
        and has_next_innings
        and not match_over
    )

    at_over_boundary = (
        derived.legal_balls > 0

        and (
            derived.legal_balls
            % match.balls_per_over
            == 0
        )

        and not innings_complete
    )

    previous_bowler = (
        previous_over_bowler_id(
            deliveries
        )
        if at_over_boundary
        else None
    )

    target = None

    runs_required = None

    balls_remaining = None

    if chase is not None:

        target = (
            chase.target
        )

        runs_required = max(
            target
            - derived.total_runs,
            0,
        )

        if (
            match.total_overs
            is not None
        ):

            balls_remaining = max(
                (
                    match.total_overs
                    * match.balls_per_over
                    - derived.legal_balls
                ),
                0,
            )

    summary = None

    if (
        chase is not None

        and (
            innings_complete
            or match.status
            == MatchStatus.COMPLETED
        )
    ):

        summary = result_summary(
            batting_team_name=(
                innings
                .batting_team
                .name
            ),

            bowling_team_name=(
                innings
                .bowling_team
                .name
            ),

            batting_runs=(
                chase.batting_runs
            ),

            bowling_runs=(
                chase.bowling_runs
            ),

            wickets=(
                derived.wickets
            ),

            players_per_side=(
                batting_side_size(match, innings)
            ),
        )

    wicket_limit = max_wickets(
        batting_side_size(match, innings)
    )

    return ScoringStateRead(
        match_id=(
            match.id
        ),

        innings_id=(
            innings.id
        ),

        innings_number=(
            innings.innings_number
        ),

        match_status=(
            match.status
        ),

        innings_status=(
            innings.status
        ),

        batting_team=(
            TeamSummary
            .model_validate(
                innings.batting_team
            )
        ),

        bowling_team=(
            TeamSummary
            .model_validate(
                innings.bowling_team
            )
        ),

        total_runs=(
            derived.total_runs
        ),

        wickets=(
            derived.wickets
        ),

        max_wickets=(
            wicket_limit
        ),

        all_out=(
            derived.wickets
            >= wicket_limit
        ),

        legal_balls=(
            derived.legal_balls
        ),

        completed_overs=(
            completed_overs
        ),

        balls_in_current_over=(
            balls_in_over
        ),

        overs=overs_display(
            derived.legal_balls,
            match.balls_per_over,
        ),

        current_run_rate=(
            current_run_rate(
                derived.total_runs,
                derived.legal_balls,
                match.balls_per_over,
            )
        ),

        total_overs=(
            match.total_overs
        ),

        balls_per_over=(
            match.balls_per_over
        ),

        overs_complete=(
            overs_complete(
                match,
                derived.legal_balls,
            )
        ),

        striker=(
            PlayerSummary
            .model_validate(
                striker
            )
        ),

        non_striker=(
            PlayerSummary
            .model_validate(
                non_striker
            )
        ),

        current_bowler=(
            PlayerSummary
            .model_validate(
                bowler
            )
        ),

        dismissed_player_ids=(
            dismissed_ids
        ),

        retired_hurt_player_ids=sorted(
            retired.retired_hurt_ids,
            key=str,
        ),

        retired_out_player_ids=sorted(
            retired.retired_out_ids,
            key=str,
        ),

        retirements=[
            retirement_read(
                item
            )
            for item
            in retirements
        ],

        retirement_blocks_undo=(
            bool(deliveries)
            and bool(
                trailing_retirements(
                    deliveries,
                    retirements,
                )
            )
        ),

        next_sequence=(
            next_sequence
        ),

        next_over_number=(
            next_over
        ),

        next_ball_number=(
            next_ball
        ),

        at_over_boundary=(
            at_over_boundary
        ),

        bowler_change_required=(
            bowler_change_required(
                legal_balls=(
                    derived.legal_balls
                ),

                balls_per_over=(
                    match.balls_per_over
                ),

                previous_bowler_id=(
                    previous_bowler
                ),

                current_bowler_id=(
                    innings
                    .current_bowler_id
                ),
            )
            if at_over_boundary
            else False
        ),

        previous_over_bowler_id=(
            previous_bowler
        ),

        recent_deliveries=[
            delivery_read(
                item
            )
            for item
            in history
        ],

        innings=[
            InningsSummary(
                innings_number=(
                    item
                    .innings_number
                ),

                status=(
                    item.status
                ),

                batting_team=(
                    TeamSummary
                    .model_validate(
                        item
                        .batting_team
                    )
                ),

                total_runs=(
                    totals.get(
                        item.id,
                        (
                            0,
                            0,
                            0,
                        ),
                    )[0]
                ),

                wickets=(
                    totals.get(
                        item.id,
                        (
                            0,
                            0,
                            0,
                        ),
                    )[2]
                ),

                legal_balls=(
                    totals.get(
                        item.id,
                        (
                            0,
                            0,
                            0,
                        ),
                    )[1]
                ),

                overs=(
                    overs_display(
                        totals.get(
                            item.id,
                            (
                                0,
                                0,
                                0,
                            ),
                        )[1],

                        match
                        .balls_per_over,
                    )
                ),
            )

            for item
            in innings_list
        ],

        innings_complete=(
            innings_complete
        ),

        can_end_innings=(
            match.total_overs
            is None

            and not innings_complete

            and not match_over

            and derived.legal_balls
            > 0
        ),

        can_start_next_innings=(
            can_start_next_innings
        ),

        next_innings_number=(
            innings.innings_number
            + 1
            if can_start_next_innings
            else None
        ),

        next_batting_team=(
            TeamSummary
            .model_validate(
                innings
                .bowling_team
            )
            if can_start_next_innings
            else None
        ),

        next_bowling_team=(
            TeamSummary
            .model_validate(
                innings
                .batting_team
            )
            if can_start_next_innings
            else None
        ),

        target=(
            target
        ),

        runs_required=(
            runs_required
        ),

        balls_remaining=(
            balls_remaining
        ),

        result_summary=(
            summary
        ),

        cache_matches_history=(
            cache_matches_history
        ),
    )


async def current_state(
    repository: ScoringRepository,
    match_id: UUID,
    after: str,
) -> ScoringStateRead:

    match = (
        await repository
        .get_match(
            match_id
        )
    )

    innings = (
        await repository
        .get_current_innings(
            match_id
        )
    )

    if (
        match is None
        or innings is None
    ):

        raise NotFoundError(
            "Scoring state not "
            f"found after {after}"
        )

    return await state_response(
        repository,
        match=match,
        innings=innings,
    )


async def get_scoring_state(
    session: AsyncSession,
    match_id: UUID,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    match = (
        await repository
        .get_match(
            match_id
        )
    )

    if match is None:

        raise NotFoundError(
            "Match not found"
        )

    if (
        match.status
        == MatchStatus.DRAFT
    ):

        raise ConflictError(
            "Complete the match "
            "setup before "
            "live scoring"
        )

    innings = (
        await repository
        .get_current_innings(
            match_id
        )
    )

    if innings is None:

        raise NotFoundError(
            "First innings has "
            "not been configured"
        )

    return await state_response(
        repository,
        match=match,
        innings=innings,
    )
