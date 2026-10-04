from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models import (
    AuditAction,
    Delivery,
    DeliveryCorrection,
    Innings,
    Match,
    Player,
)
from app.models.enums import (
    CorrectionType,
    DeliveryStatus,
    InningsStatus,
    MatchStatus,
    WicketType,
)
from app.repositories.scoring import (
    ScoringRepository,
)
from app.schemas.match_setup import (
    PlayerSummary,
    TeamSummary,
)
from app.schemas.scoring import (
    BowlerChange,
    DeliveryCreate,
    DeliveryRead,
    DeliveryUndo,
    InningsSummary,
    NextInningsCreate,
    ScoringStateRead,
    WicketCreate,
)
from app.services.common import (
    add_audit_log,
    integrity_conflict,
    service_transaction,
)


RUN_OUTCOMES = {
    0,
    1,
    2,
    3,
    4,
    6,
}


@dataclass(frozen=True)
class DerivedState:
    total_runs: int
    legal_balls: int
    wickets: int
    striker_id: UUID
    non_striker_id: UUID


@dataclass(frozen=True)
class DeliveryComponents:
    batter_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    extra_runs: int
    total_runs: int
    running_runs: int
    is_legal_ball: bool


def ball_position(legal_balls_before: int, balls_per_over: int) -> tuple[int, int]:
    if legal_balls_before < 0:
        raise ValueError(
            "legal_balls_before "
            "cannot be negative"
        )

    if balls_per_over <= 0:
        raise ValueError(
            "balls_per_over "
            "must be positive"
        )

    return (
        legal_balls_before
        // balls_per_over
        + 1,

        legal_balls_before
        % balls_per_over
        + 1,
    )


def overs_parts(legal_balls: int, balls_per_over: int) -> tuple[int, int]:
    if legal_balls < 0:
        raise ValueError(
            "legal_balls cannot "
            "be negative"
        )

    if balls_per_over <= 0:
        raise ValueError(
            "balls_per_over "
            "must be positive"
        )

    return divmod(
        legal_balls,
        balls_per_over,
    )


def overs_display(legal_balls: int, balls_per_over: int) -> str:

    completed_overs, balls = (
        overs_parts(
            legal_balls,
            balls_per_over,
        )
    )

    return (
        f"{completed_overs}."
        f"{balls}"
    )


def current_run_rate(
    total_runs: int,
    legal_balls: int,
    balls_per_over: int,
) -> float:

    if legal_balls == 0:
        return 0.0

    return round(
        total_runs
        * balls_per_over
        / legal_balls,
        2,
    )


def advance_batters(
    striker_id: UUID,
    non_striker_id: UUID,
    *,
    runs: int,
    legal_balls_after: int,
    balls_per_over: int,
) -> tuple[
    UUID,
    UUID,
]:
    """
    Stage 4 helper kept so your
    existing tests continue working.
    """

    if runs not in RUN_OUTCOMES:
        raise ValueError(
            "Unsupported normal "
            "run outcome"
        )

    striker = striker_id

    non_striker = (
        non_striker_id
    )

    if runs % 2 == 1:

        (
            striker,
            non_striker,
        ) = (
            non_striker,
            striker,
        )

    if (
        legal_balls_after
        % balls_per_over
        == 0
    ):

        (
            striker,
            non_striker,
        ) = (
            non_striker,
            striker,
        )

    return (
        striker,
        non_striker,
    )


def delivery_components(
    payload: DeliveryCreate,
) -> DeliveryComponents:
    """
    Convert the API event into
    official run components.

    Important:

    - WD/NB are illegal balls.
    - BYE/LB remain legal balls.
    - NB adds one automatic extra.
    - automatic WD/NB penalty does
      not itself rotate strike.
    """

    no_ball_runs = (
        1
        if payload.no_ball
        else 0
    )

    extra_runs = (
        payload.wide_runs
        + no_ball_runs
        + payload.bye_runs
        + payload.leg_bye_runs
    )

    # Runs which physically move
    # batters between ends.
    running_runs = (
        payload.runs
        + payload.bye_runs
        + payload.leg_bye_runs
        + max(
            payload.wide_runs - 1,
            0,
        )
    )

    return DeliveryComponents(
        batter_runs=payload.runs,

        wide_runs=(
            payload.wide_runs
        ),

        no_ball_runs=(
            no_ball_runs
        ),

        bye_runs=(
            payload.bye_runs
        ),

        leg_bye_runs=(
            payload.leg_bye_runs
        ),

        extra_runs=(
            extra_runs
        ),

        total_runs=(
            payload.runs
            + extra_runs
        ),

        running_runs=(
            running_runs
        ),

        is_legal_ball=(
            payload.wide_runs == 0
            and not payload.no_ball
        ),
    )


def _delivery_running_runs(
    delivery: Delivery,
) -> int:

    # Compatibility with the old
    # Stage 4 SimpleNamespace tests.
    if not hasattr(
        delivery,
        "wide_runs",
    ):
        return int(
            delivery.total_runs
        )

    return int(
        delivery.batter_runs
        + delivery.bye_runs
        + delivery.leg_bye_runs
        + max(
            delivery.wide_runs
            - 1,
            0,
        )
    )


def _post_delivery_batters(
    *,
    striker_id: UUID,
    non_striker_id: UUID,
    running_runs: int,
    is_legal_ball: bool,
    legal_balls_after: int,
    balls_per_over: int,
    dismissed_player_id: (
        UUID | None
    ) = None,
    next_batter_id: (
        UUID | None
    ) = None,
    wicket_end: (
        str | None
    ) = None,
) -> tuple[
    UUID,
    UUID,
]:
    """
    Calculate the players at the
    crease after an event.

    Strike movement comes from
    completed/running runs, not
    automatic penalty runs.
    """

    striker_end = (
        striker_id
    )

    non_striker_end = (
        non_striker_id
    )

    # Batters changed physical ends.
    if running_runs % 2 == 1:

        (
            striker_end,
            non_striker_end,
        ) = (
            non_striker_end,
            striker_end,
        )

    if (
        dismissed_player_id
        is not None
    ):

        survivor_id = (
            non_striker_id
            if (
                dismissed_player_id
                == striker_id
            )
            else striker_id
        )

        # When all out there is no
        # replacement. Retaining the
        # dismissed player's ID keeps
        # the final state readable.
        replacement = (
            next_batter_id
            or dismissed_player_id
        )

        # Exact run-out end supplied.
        if (
            wicket_end
            == "striker_end"
        ):

            striker_end = (
                replacement
            )

            non_striker_end = (
                survivor_id
            )

        elif (
            wicket_end
            == "non_striker_end"
        ):

            striker_end = (
                survivor_id
            )

            non_striker_end = (
                replacement
            )

        elif (
            striker_end
            == dismissed_player_id
        ):

            striker_end = (
                replacement
            )

        elif (
            non_striker_end
            == dismissed_player_id
        ):

            non_striker_end = (
                replacement
            )

        else:

            # Defensive fallback for
            # unusual run-out movement.
            striker_end = (
                replacement
            )

            non_striker_end = (
                survivor_id
            )

    # Only a legal delivery can
    # complete an over.
    if (
        is_legal_ball
        and legal_balls_after
        % balls_per_over
        == 0
    ):

        return (
            non_striker_end,
            striker_end,
        )

    return (
        striker_end,
        non_striker_end,
    )


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
    ) = _post_delivery_batters(
        striker_id=(
            last.striker_id
        ),

        non_striker_id=(
            last.non_striker_id
        ),

        running_runs=(
            _delivery_running_runs(
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


def _overs_complete(
    match: Match,
    legal_balls: int,
) -> bool:

    if match.total_overs is None:
        return False

    return (
        legal_balls
        >= (
            match.total_overs
            * match.balls_per_over
        )
    )


def max_innings(
    innings_per_team: int,
) -> int:

    return (
        innings_per_team
        * 2
    )


def max_wickets(
    players_per_side: int,
) -> int:

    return max(
        players_per_side - 1,
        1,
    )


def previous_over_bowler_id(
    deliveries: list[
        Delivery
    ],
) -> UUID | None:

    for delivery in reversed(
        deliveries
    ):

        if delivery.is_legal_ball:

            return (
                delivery.bowler_id
            )

    return None


def bowler_change_required(
    *,
    legal_balls: int,
    balls_per_over: int,
    previous_bowler_id: (
        UUID | None
    ),
    current_bowler_id: (
        UUID | None
    ),
) -> bool:

    if legal_balls == 0:
        return False

    if (
        legal_balls
        % balls_per_over
        != 0
    ):
        return False

    return (
        current_bowler_id
        == previous_bowler_id
    )


def chase_target(
    *,
    opponent_runs: int,
    batting_previous_runs: int,
) -> int:

    return (
        opponent_runs
        - batting_previous_runs
        + 1
    )


def result_summary(
    *,
    batting_team_name: str,
    bowling_team_name: str,
    batting_runs: int,
    bowling_runs: int,
    wickets: int,
    players_per_side: int,
) -> str:

    if batting_runs > bowling_runs:

        margin = max(
            players_per_side
            - 1
            - wickets,
            1,
        )

        unit = (
            "wicket"
            if margin == 1
            else "wickets"
        )

        return (
            f"{batting_team_name} "
            f"won by "
            f"{margin} "
            f"{unit}"
        )

    if (
        batting_runs
        == bowling_runs
    ):

        return "Match tied"

    margin = (
        bowling_runs
        - batting_runs
    )

    unit = (
        "run"
        if margin == 1
        else "runs"
    )

    return (
        f"{bowling_team_name} "
        f"won by "
        f"{margin} "
        f"{unit}"
    )


def _team_runs(
    innings_list: list[
        Innings
    ],
    totals: dict[
        UUID,
        tuple[
            int,
            int,
            int,
        ],
    ],
    team_id: UUID,
    *,
    exclude_innings_id: (
        UUID | None
    ) = None,
) -> int:

    return sum(
        totals.get(
            item.id,
            (
                0,
                0,
                0,
            ),
        )[0]

        for item
        in innings_list

        if (
            item.batting_team_id
            == team_id

            and item.id
            != exclude_innings_id
        )
    )


@dataclass(
    frozen=True
)
class ChaseState:

    target: int

    batting_runs: int

    bowling_runs: int


def _chase_state(
    match: Match,
    innings: Innings,
    innings_list: list[
        Innings
    ],
    totals: dict[
        UUID,
        tuple[
            int,
            int,
            int,
        ],
    ],
) -> ChaseState | None:

    if (
        innings.innings_number
        < max_innings(
            match.innings_per_team
        )
    ):

        return None

    batting_previous = (
        _team_runs(
            innings_list,
            totals,
            innings.batting_team_id,
            exclude_innings_id=(
                innings.id
            ),
        )
    )

    bowling_runs = (
        _team_runs(
            innings_list,
            totals,
            innings.bowling_team_id,
        )
    )

    current_runs = (
        totals.get(
            innings.id,
            (
                0,
                0,
                0,
            ),
        )[0]
    )

    return ChaseState(
        target=chase_target(
            opponent_runs=(
                bowling_runs
            ),

            batting_previous_runs=(
                batting_previous
            ),
        ),

        batting_runs=(
            batting_previous
            + current_runs
        ),

        bowling_runs=(
            bowling_runs
        ),
    )


def _innings_finished(
    match: Match,
    innings: Innings,
    legal_balls: int,
    wickets: int,
    chase: (
        ChaseState | None
    ),
) -> bool:

    if (
        innings.status
        == InningsStatus.COMPLETED
    ):
        return True

    if (
        wickets
        >= max_wickets(
            match.players_per_side
        )
    ):
        return True

    if _overs_complete(
        match,
        legal_balls,
    ):
        return True

    return (
        chase is not None
        and chase.batting_runs
        > chase.bowling_runs
    )


def _close_innings(
    match: Match,
    innings: Innings,
) -> None:

    innings.status = (
        InningsStatus.COMPLETED
    )

    if (
        innings.innings_number
        >= max_innings(
            match.innings_per_team
        )
    ):

        match.status = (
            MatchStatus.COMPLETED
        )

    else:

        match.status = (
            MatchStatus.INNINGS_BREAK
        )


def _ensure_scoreable(
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


async def _player_or_error(
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


def _player_summary(
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


def _delivery_read(
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
            _player_summary(
                item.dismissed_player
            )
        ),

        fielder=(
            _player_summary(
                item.fielder
            )
        ),

        next_batter=(
            _player_summary(
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


async def _validate_wicket(
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


async def _state_response(
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

    derived = (
        rebuild_from_deliveries(
            innings,
            deliveries,
            balls_per_over=(
                match.balls_per_over
            ),
        )
    )

    striker = (
        await _player_or_error(
            repository,
            derived.striker_id,
            "Striker",
        )
    )

    non_striker = (
        await _player_or_error(
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
        await _player_or_error(
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
        {
            item.dismissed_player_id
            for item
            in deliveries
            if (
                item.dismissed_player_id
                is not None
            )
        },
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

    chase = _chase_state(
        match,
        innings,
        innings_list,
        totals,
    )

    innings_complete = (
        _innings_finished(
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
                match.players_per_side
            ),
        )

    wicket_limit = max_wickets(
        match.players_per_side
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
            _overs_complete(
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
            _delivery_read(
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


async def _current_state(
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

    return await _state_response(
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

    return await _state_response(
        repository,
        match=match,
        innings=innings,
    )


async def record_delivery(
    session: AsyncSession,
    match_id: UUID,
    payload: DeliveryCreate,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    try:

        async with service_transaction(
            session
        ):

            innings = (
                await repository
                .lock_current_innings(
                    match_id
                )
            )

            if innings is None:

                raise NotFoundError(
                    "First innings has "
                    "not been configured"
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

            _ensure_scoreable(
                match,
                innings,
            )

            deliveries = (
                await repository
                .get_recorded_deliveries_plain(
                    innings.id
                )
            )

            before = (
                rebuild_from_deliveries(
                    innings,
                    deliveries,
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
            )

            if _overs_complete(
                match,
                before.legal_balls,
            ):

                raise ConflictError(
                    "The configured "
                    "over limit has "
                    "been reached for "
                    "this innings"
                )

            if (
                before.wickets
                >= max_wickets(
                    match
                    .players_per_side
                )
            ):

                raise ConflictError(
                    "The batting side "
                    "is already all out"
                )

            if (
                innings.current_bowler_id
                is None
            ):

                raise ValidationError(
                    "Current bowler "
                    "is not configured"
                )

            if bowler_change_required(
                legal_balls=(
                    before.legal_balls
                ),

                balls_per_over=(
                    match
                    .balls_per_over
                ),

                previous_bowler_id=(
                    previous_over_bowler_id(
                        deliveries
                    )
                ),

                current_bowler_id=(
                    innings
                    .current_bowler_id
                ),
            ):

                raise ConflictError(
                    "Over complete. "
                    "Select a different "
                    "bowler for the "
                    "next over"
                )

            components = (
                delivery_components(
                    payload
                )
            )

            if (
                payload.wicket
                is not None
            ):

                await _validate_wicket(
                    repository,

                    match=match,

                    innings=innings,

                    before=before,

                    components=(
                        components
                    ),

                    wicket=(
                        payload.wicket
                    ),
                )

            (
                over_number,
                ball_number,
            ) = ball_position(
                before.legal_balls,
                match.balls_per_over,
            )

            sequence = (
                await repository
                .next_delivery_number(
                    innings.id
                )
            )

            wicket = (
                payload.wicket
            )

            delivery = Delivery(
                match_id=(
                    match.id
                ),

                innings_id=(
                    innings.id
                ),

                delivery_number=(
                    sequence
                ),

                over_number=(
                    over_number
                ),

                ball_number=(
                    ball_number
                ),

                striker_id=(
                    before.striker_id
                ),

                non_striker_id=(
                    before
                    .non_striker_id
                ),

                bowler_id=(
                    innings
                    .current_bowler_id
                ),

                batter_runs=(
                    components
                    .batter_runs
                ),

                extra_runs=(
                    components
                    .extra_runs
                ),

                wide_runs=(
                    components
                    .wide_runs
                ),

                no_ball_runs=(
                    components
                    .no_ball_runs
                ),

                bye_runs=(
                    components
                    .bye_runs
                ),

                leg_bye_runs=(
                    components
                    .leg_bye_runs
                ),

                total_runs=(
                    components
                    .total_runs
                ),

                is_legal_ball=(
                    components
                    .is_legal_ball
                ),

                wicket_type=(
                    wicket.wicket_type
                    if wicket
                    else None
                ),

                dismissed_player_id=(
                    wicket
                    .dismissed_player_id
                    if wicket
                    else None
                ),

                fielder_id=(
                    wicket.fielder_id
                    if wicket
                    else None
                ),

                next_batter_id=(
                    wicket
                    .next_batter_id
                    if wicket
                    else None
                ),

                wicket_end=(
                    wicket.wicket_end
                    if wicket
                    else None
                ),

                status=(
                    DeliveryStatus
                    .RECORDED
                ),

                actor_id=None,
            )

            session.add(
                delivery
            )

            await session.flush()

            after_legal = (
                before.legal_balls

                + (
                    1
                    if components
                    .is_legal_ball
                    else 0
                )
            )

            after_wickets = (
                before.wickets

                + (
                    1
                    if wicket
                    is not None
                    else 0
                )
            )

            (
                after_striker,
                after_non_striker,
            ) = _post_delivery_batters(
                striker_id=(
                    before.striker_id
                ),

                non_striker_id=(
                    before
                    .non_striker_id
                ),

                running_runs=(
                    components
                    .running_runs
                ),

                is_legal_ball=(
                    components
                    .is_legal_ball
                ),

                legal_balls_after=(
                    after_legal
                ),

                balls_per_over=(
                    match
                    .balls_per_over
                ),

                dismissed_player_id=(
                    wicket
                    .dismissed_player_id
                    if wicket
                    else None
                ),

                next_batter_id=(
                    wicket
                    .next_batter_id
                    if wicket
                    else None
                ),

                wicket_end=(
                    wicket.wicket_end
                    if wicket
                    else None
                ),
            )

            # Rebuildable caches.
            innings.total_runs = (
                before.total_runs
                + components.total_runs
            )

            innings.wickets = (
                after_wickets
            )

            innings.legal_balls = (
                after_legal
            )

            innings.striker_id = (
                after_striker
            )

            innings.non_striker_id = (
                after_non_striker
            )

            innings.status = (
                InningsStatus.LIVE
            )

            if (
                match.status
                == MatchStatus.READY
            ):

                match.status = (
                    MatchStatus.LIVE
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

            chase = _chase_state(
                match,
                innings,
                innings_list,
                totals,
            )

            if _innings_finished(
                match,
                innings,
                after_legal,
                after_wickets,
                chase,
            ):

                _close_innings(
                    match,
                    innings,
                )

            add_audit_log(
                session,

                entity_type=(
                    "delivery"
                ),

                entity_id=(
                    delivery.id
                ),

                action=(
                    AuditAction.CREATED
                ),

                details={
                    "match_id":
                        str(
                            match.id
                        ),

                    "innings_id":
                        str(
                            innings.id
                        ),

                    "sequence":
                        sequence,

                    "over_number":
                        over_number,

                    "ball_number":
                        ball_number,

                    "batter_runs":
                        components
                        .batter_runs,

                    "wide_runs":
                        components
                        .wide_runs,

                    "no_ball_runs":
                        components
                        .no_ball_runs,

                    "bye_runs":
                        components
                        .bye_runs,

                    "leg_bye_runs":
                        components
                        .leg_bye_runs,

                    "total_runs":
                        components
                        .total_runs,

                    "wicket_type":
                        (
                            wicket
                            .wicket_type
                            .value

                            if wicket

                            else None
                        ),

                    "dismissed_player_id":
                        (
                            str(
                                wicket
                                .dismissed_player_id
                            )

                            if wicket

                            else None
                        ),

                    "next_batter_id":
                        (
                            str(
                                wicket
                                .next_batter_id
                            )

                            if (
                                wicket
                                and wicket
                                .next_batter_id
                            )

                            else None
                        ),
                },
            )

            await session.flush()

        return await _current_state(
            repository,
            match_id,
            "delivery commit",
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Delivery",
        ) from error


async def undo_delivery(
    session: AsyncSession,
    match_id: UUID,
    delivery_id: UUID,
    payload: DeliveryUndo,
) -> ScoringStateRead:
    """
    Safe Stage 5 undo.

    We intentionally only allow the
    latest official delivery to be
    undone. That prevents a scorer
    from voiding an old event while
    leaving later participant states
    inconsistent.

    History is never deleted.
    """

    repository = (
        ScoringRepository(
            session
        )
    )

    async with service_transaction(
        session
    ):

        innings = (
            await repository
            .lock_current_innings(
                match_id
            )
        )

        if innings is None:

            raise NotFoundError(
                "First innings has "
                "not been configured"
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

        delivery = (
            await repository
            .get_delivery_for_update(
                match_id=(
                    match_id
                ),

                delivery_id=(
                    delivery_id
                ),
            )
        )

        if delivery is None:

            raise NotFoundError(
                "Delivery not found"
            )

        if (
            delivery.innings_id
            != innings.id
        ):

            raise ConflictError(
                "Only the current "
                "innings can be "
                "corrected in Stage 5"
            )

        if (
            delivery.status
            != DeliveryStatus.RECORDED
        ):

            raise ConflictError(
                "This delivery has "
                "already been voided"
            )

        latest = (
            await repository
            .last_recorded_delivery(
                innings.id
            )
        )

        if (
            latest is None
            or latest.id
            != delivery.id
        ):

            raise ConflictError(
                "Stage 5 safe undo "
                "can only void the "
                "most recent official "
                "delivery"
            )

        # ======================
        # PRESERVE HISTORY
        # ======================

        delivery.status = (
            DeliveryStatus.VOID
        )

        correction = (
            DeliveryCorrection(
                delivery_id=(
                    delivery.id
                ),

                correction_type=(
                    CorrectionType.VOID
                ),

                reason=(
                    payload.reason
                ),

                actor_id=None,
            )
        )

        session.add(
            correction
        )

        add_audit_log(
            session,

            entity_type=(
                "delivery"
            ),

            entity_id=(
                delivery.id
            ),

            action=(
                AuditAction.CORRECTED
            ),

            details={
                "correction_type":
                    CorrectionType
                    .VOID
                    .value,

                "reason":
                    payload.reason,

                "sequence":
                    delivery
                    .delivery_number,
            },
        )

        await session.flush()

        # ======================
        # REBUILD STATE
        # ======================

        remaining = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        if remaining:

            rebuilt = (
                rebuild_from_deliveries(
                    innings,
                    remaining,
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
            )

        else:

            # The now-void delivery
            # stores the exact state
            # immediately before it.
            rebuilt = DerivedState(
                total_runs=0,

                legal_balls=0,

                wickets=0,

                striker_id=(
                    delivery
                    .striker_id
                ),

                non_striker_id=(
                    delivery
                    .non_striker_id
                ),
            )

        innings.total_runs = (
            rebuilt.total_runs
        )

        innings.wickets = (
            rebuilt.wickets
        )

        innings.legal_balls = (
            rebuilt.legal_balls
        )

        innings.striker_id = (
            rebuilt.striker_id
        )

        innings.non_striker_id = (
            rebuilt.non_striker_id
        )

        # This is exactly the bowler
        # selected immediately before
        # the voided event.
        innings.current_bowler_id = (
            delivery.bowler_id
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

        chase = _chase_state(
            match,
            innings,
            innings_list,
            totals,
        )

        # Important: undo may reopen
        # an innings or completed match.
        innings.status = (
            InningsStatus.LIVE
            if remaining
            else InningsStatus.PENDING
        )

        if _innings_finished(
            match,
            innings,
            rebuilt.legal_balls,
            rebuilt.wickets,
            chase,
        ):

            _close_innings(
                match,
                innings,
            )

        else:

            match.status = (
                MatchStatus.READY

                if (
                    innings.innings_number
                    == 1
                    and not remaining
                )

                else MatchStatus.LIVE
            )

        await session.flush()

    return await _current_state(
        repository,
        match_id,
        "delivery undo",
    )


async def change_bowler(
    session: AsyncSession,
    match_id: UUID,
    payload: BowlerChange,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    async with service_transaction(
        session
    ):

        innings = (
            await repository
            .lock_current_innings(
                match_id
            )
        )

        if innings is None:

            raise NotFoundError(
                "First innings has "
                "not been configured"
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

        _ensure_scoreable(
            match,
            innings,
        )

        deliveries = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        derived = (
            rebuild_from_deliveries(
                innings,
                deliveries,
                balls_per_over=(
                    match
                    .balls_per_over
                ),
            )
        )

        if (
            derived.legal_balls
            == 0
        ):

            raise ConflictError(
                "The opening bowler "
                "is already configured "
                "for this innings"
            )

        if (
            derived.legal_balls
            % match.balls_per_over
            != 0
        ):

            raise ConflictError(
                "Bowler can only "
                "be changed at an "
                "over boundary"
            )

        if _overs_complete(
            match,
            derived.legal_balls,
        ):

            raise ConflictError(
                "The configured "
                "over limit has "
                "been reached"
            )

        if (
            payload.bowler_id
            == previous_over_bowler_id(
                deliveries
            )
        ):

            raise ValidationError(
                "This bowler bowled "
                "the previous over. "
                "Choose a different "
                "bowler"
            )

        belongs = (
            await repository
            .is_playing_team_player(
                match_id=(
                    match.id
                ),

                team_id=(
                    innings
                    .bowling_team_id
                ),

                player_id=(
                    payload
                    .bowler_id
                ),
            )
        )

        if not belongs:

            raise ValidationError(
                "Bowler must belong "
                "to the bowling "
                "team's selected "
                "playing team"
            )

        player = (
            await repository
            .get_player(
                payload.bowler_id
            )
        )

        if player is None:

            raise NotFoundError(
                "Bowler not found"
            )

        innings.current_bowler_id = (
            payload.bowler_id
        )

        add_audit_log(
            session,

            entity_type=(
                "innings"
            ),

            entity_id=(
                innings.id
            ),

            action=(
                AuditAction.UPDATED
            ),

            details={
                "setup":
                    "current_bowler",

                "bowler_id":
                    str(
                        payload
                        .bowler_id
                    ),

                "after_legal_balls":
                    derived
                    .legal_balls,
            },
        )

        await session.flush()

    return await _current_state(
        repository,
        match_id,
        "bowler change",
    )


async def end_innings(
    session: AsyncSession,
    match_id: UUID,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    async with service_transaction(
        session
    ):

        innings = (
            await repository
            .lock_current_innings(
                match_id
            )
        )

        if innings is None:

            raise NotFoundError(
                "First innings has "
                "not been configured"
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

        _ensure_scoreable(
            match,
            innings,
        )

        if (
            match.total_overs
            is not None
        ):

            raise ConflictError(
                "Limited-overs "
                "innings end "
                "automatically when "
                "the over limit is "
                "reached"
            )

        deliveries = (
            await repository
            .get_recorded_deliveries_plain(
                innings.id
            )
        )

        if not deliveries:

            raise ConflictError(
                "Record at least one "
                "delivery before "
                "ending the innings"
            )

        _close_innings(
            match,
            innings,
        )

        add_audit_log(
            session,

            entity_type=(
                "innings"
            ),

            entity_id=(
                innings.id
            ),

            action=(
                AuditAction.UPDATED
            ),

            details={
                "setup":
                    "innings_ended",

                "innings_number":
                    innings
                    .innings_number,
            },
        )

        await session.flush()

    return await _current_state(
        repository,
        match_id,
        "ending the innings",
    )


async def start_next_innings(
    session: AsyncSession,
    match_id: UUID,
    payload: NextInningsCreate,
) -> ScoringStateRead:

    repository = (
        ScoringRepository(
            session
        )
    )

    try:

        async with service_transaction(
            session
        ):

            previous = (
                await repository
                .lock_current_innings(
                    match_id
                )
            )

            if previous is None:

                raise NotFoundError(
                    "First innings has "
                    "not been configured"
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
                in {
                    MatchStatus.COMPLETED,
                    MatchStatus.ABANDONED,
                }
            ):

                raise ConflictError(
                    "The match is "
                    "already finished"
                )

            next_number = (
                previous
                .innings_number
                + 1
            )

            if (
                next_number
                > max_innings(
                    match
                    .innings_per_team
                )
            ):

                raise ConflictError(
                    "All innings for "
                    "this match have "
                    "been played"
                )

            deliveries = (
                await repository
                .get_recorded_deliveries_plain(
                    previous.id
                )
            )

            derived = (
                rebuild_from_deliveries(
                    previous,
                    deliveries,
                    balls_per_over=(
                        match
                        .balls_per_over
                    ),
                )
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

            chase = _chase_state(
                match,
                previous,
                innings_list,
                totals,
            )

            if not _innings_finished(
                match,
                previous,
                derived.legal_balls,
                derived.wickets,
                chase,
            ):

                raise ConflictError(
                    f"Innings "
                    f"{previous.innings_number} "
                    "is still in progress"
                )

            batting_team_id = (
                previous
                .bowling_team_id
            )

            bowling_team_id = (
                previous
                .batting_team_id
            )

            for (
                player_id,
                team_id,
                label,
            ) in (
                (
                    payload
                    .striker_id,

                    batting_team_id,

                    "Striker",
                ),

                (
                    payload
                    .non_striker_id,

                    batting_team_id,

                    "Non-striker",
                ),

                (
                    payload
                    .opening_bowler_id,

                    bowling_team_id,

                    "Opening bowler",
                ),
            ):

                side = (
                    "batting"

                    if (
                        team_id
                        == batting_team_id
                    )

                    else "bowling"
                )

                belongs = (
                    await repository
                    .is_playing_team_player(
                        match_id=(
                            match.id
                        ),

                        team_id=(
                            team_id
                        ),

                        player_id=(
                            player_id
                        ),
                    )
                )

                if not belongs:

                    raise ValidationError(
                        f"{label} must "
                        f"belong to the "
                        f"{side} team's "
                        "playing team"
                    )

            previous.status = (
                InningsStatus.COMPLETED
            )

            innings = Innings(
                match_id=(
                    match.id
                ),

                innings_number=(
                    next_number
                ),

                batting_team_id=(
                    batting_team_id
                ),

                bowling_team_id=(
                    bowling_team_id
                ),

                status=(
                    InningsStatus.PENDING
                ),

                striker_id=(
                    payload.striker_id
                ),

                non_striker_id=(
                    payload
                    .non_striker_id
                ),

                current_bowler_id=(
                    payload
                    .opening_bowler_id
                ),
            )

            session.add(
                innings
            )

            match.status = (
                MatchStatus.LIVE
            )

            await session.flush()

            add_audit_log(
                session,

                entity_type=(
                    "innings"
                ),

                entity_id=(
                    innings.id
                ),

                action=(
                    AuditAction.CREATED
                ),

                details={
                    "setup":
                        "next_innings",

                    "innings_number":
                        next_number,

                    "striker_id":
                        str(
                            payload
                            .striker_id
                        ),

                    "non_striker_id":
                        str(
                            payload
                            .non_striker_id
                        ),

                    "opening_bowler_id":
                        str(
                            payload
                            .opening_bowler_id
                        ),
                },
            )

            await session.flush()

        return await _current_state(
            repository,
            match_id,
            "starting the innings",
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Innings",
        ) from error