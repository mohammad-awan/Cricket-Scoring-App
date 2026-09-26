from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    AuditAction,
    Delivery,
    Innings,
    Match,
    Player,
)
from app.models.enums import DeliveryStatus, InningsStatus, MatchStatus
from app.repositories.scoring import ScoringRepository
from app.schemas.match_setup import PlayerSummary, TeamSummary
from app.schemas.scoring import (
    BowlerChange,
    DeliveryCreate,
    DeliveryRead,
    InningsSummary,
    NextInningsCreate,
    ScoringStateRead,
)
from app.services.common import add_audit_log, integrity_conflict, service_transaction


RUN_OUTCOMES = {0, 1, 2, 3, 4, 6,}


@dataclass(frozen=True)
class DerivedState:
    total_runs: int
    legal_balls: int
    striker_id: UUID
    non_striker_id: UUID


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

    over_number = (
        legal_balls_before
        // balls_per_over
        + 1
    )

    ball_number = (
        legal_balls_before
        % balls_per_over
        + 1
    )

    return (
        over_number,
        ball_number,
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

    return divmod(legal_balls, balls_per_over)


def overs_display(legal_balls: int, balls_per_over: int) -> str:
    completed_overs, balls = (overs_parts(legal_balls, balls_per_over))

    return (
        f"{completed_overs}."
        f"{balls}"
    )


def current_run_rate(total_runs: int, legal_balls: int, balls_per_over: int) -> float:
    if legal_balls == 0:
        return 0.0

    value = total_runs * balls_per_over / legal_balls

    return round(value, 2)


def advance_batters(
    striker_id: UUID,
    non_striker_id: UUID,
    *,
    runs: int,
    legal_balls_after: int,
    balls_per_over: int,
) -> tuple[UUID, UUID]:

    if runs not in RUN_OUTCOMES:
        raise ValueError(
            "Unsupported normal "
            "run outcome"
        )

    striker = striker_id
    non_striker = non_striker_id

    # 1 and 3 rotate strike.
    if runs % 2 == 1:
        striker, non_striker = non_striker, striker

    # End of over changes ends again.
    if legal_balls_after % balls_per_over == 0:
        striker, non_striker = non_striker, striker
    return striker, non_striker


def rebuild_from_deliveries(
    innings: Innings,
    deliveries: list[Delivery],
    *,
    balls_per_over: int,
) -> DerivedState:
    """
    Delivery history is authoritative.

    Innings.total_runs,
    Innings.legal_balls,
    Innings.striker_id and
    Innings.non_striker_id are treated
    only as rebuildable cached state.
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

            striker_id=(
                innings.striker_id
            ),

            non_striker_id=(
                innings.non_striker_id
            ),
        )

    total_runs = 0
    legal_balls = 0

    for delivery in deliveries:
        total_runs += delivery.total_runs

        if delivery.is_legal_ball:
            legal_balls += 1

    last_delivery = deliveries[-1]

    (
        striker_id,
        non_striker_id,
    ) = advance_batters(
        last_delivery.striker_id,
        last_delivery.non_striker_id,

        runs=(last_delivery.total_runs),
        legal_balls_after=(legal_balls),
        balls_per_over=(balls_per_over),
    )

    return DerivedState(
        total_runs=total_runs,
        legal_balls=legal_balls,

        striker_id=striker_id,
        non_striker_id=(
            non_striker_id
        ),
    )


def _overs_complete(match: Match, legal_balls: int) -> bool:
    # None means unlimited overs,
    # preserving your Stage 3 rule.
    if match.total_overs is None:
        return False

    maximum_balls = (
        match.total_overs
        * match.balls_per_over
    )

    return legal_balls >= maximum_balls


def max_innings(innings_per_team: int) -> int:
    return innings_per_team * 2


def previous_over_bowler_id(deliveries: list[Delivery]) -> UUID | None:
    """Bowler of the last legal ball, i.e. of the over just finished."""

    for delivery in reversed(deliveries):
        if delivery.is_legal_ball:
            return delivery.bowler_id

    return None


def bowler_change_required(
    *,
    legal_balls: int,
    balls_per_over: int,
    previous_bowler_id: UUID | None,
    current_bowler_id: UUID | None,
) -> bool:
    """
    A bowler may not bowl two
    consecutive overs.

    At an over boundary the bowler of
    the finished over must be replaced
    before the next ball is recorded.
    """

    if legal_balls == 0:
        return False

    if legal_balls % balls_per_over != 0:
        return False

    return current_bowler_id == previous_bowler_id


def chase_target(*, opponent_runs: int, batting_previous_runs: int) -> int:
    return opponent_runs - batting_previous_runs + 1


def result_summary(
    *,
    batting_team_name: str,
    bowling_team_name: str,
    batting_runs: int,
    bowling_runs: int,
    wickets: int,
    players_per_side: int,
) -> str:
    """Result from the side batting in the final innings."""

    if batting_runs > bowling_runs:
        margin = max(players_per_side - 1 - wickets, 1)
        unit = "wicket" if margin == 1 else "wickets"

        return f"{batting_team_name} won by {margin} {unit}"

    if batting_runs == bowling_runs:
        return "Match tied"

    margin = bowling_runs - batting_runs
    unit = "run" if margin == 1 else "runs"

    return f"{bowling_team_name} won by {margin} {unit}"


def _team_runs(
    innings_list: list[Innings],
    totals: dict[UUID, tuple[int, int]],
    team_id: UUID,
    *,
    exclude_innings_id: UUID | None = None,
) -> int:
    return sum(
        totals.get(item.id, (0, 0))[0]
        for item in innings_list
        if item.batting_team_id == team_id
        and item.id != exclude_innings_id
    )


@dataclass(frozen=True)
class ChaseState:
    target: int
    batting_runs: int
    bowling_runs: int


def _chase_state(
    match: Match,
    innings: Innings,
    innings_list: list[Innings],
    totals: dict[UUID, tuple[int, int]],
) -> ChaseState | None:
    """Target and aggregates, only for the final innings."""

    if innings.innings_number < max_innings(match.innings_per_team):
        return None

    batting_previous = _team_runs(
        innings_list,
        totals,
        innings.batting_team_id,
        exclude_innings_id=innings.id,
    )
    bowling_runs = _team_runs(
        innings_list,
        totals,
        innings.bowling_team_id,
    )
    current_runs = totals.get(innings.id, (0, 0))[0]

    return ChaseState(
        target=chase_target(
            opponent_runs=bowling_runs,
            batting_previous_runs=batting_previous,
        ),
        batting_runs=batting_previous + current_runs,
        bowling_runs=bowling_runs,
    )


def _innings_finished(
    match: Match,
    innings: Innings,
    legal_balls: int,
    chase: ChaseState | None,
) -> bool:
    if innings.status == InningsStatus.COMPLETED:
        return True

    if _overs_complete(match, legal_balls):
        return True

    # Target reached in the final innings.
    return chase is not None and chase.batting_runs > chase.bowling_runs


def _close_innings(match: Match, innings: Innings) -> None:
    innings.status = InningsStatus.COMPLETED

    if innings.innings_number >= max_innings(match.innings_per_team):
        match.status = MatchStatus.COMPLETED
    else:
        match.status = MatchStatus.INNINGS_BREAK


def _ensure_scoreable(match: Match, innings: Innings) -> None:
    if match.status not in {
        MatchStatus.READY,
        MatchStatus.LIVE,
    }:

        raise ConflictError(
            "Scoring is allowed only "
            "when the match is "
            "ready or live"
        )

    if innings.status not in {InningsStatus.PENDING, InningsStatus.LIVE}:
        raise ConflictError(
            f"Innings {innings.innings_number} "
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


async def _player_or_error(repository: ScoringRepository, player_id: UUID, label: str) -> Player:
    player = await repository.get_player(player_id)

    if player is None:
        raise NotFoundError(f"{label} not found")

    return player


def _delivery_read(item: Delivery) -> DeliveryRead:
    return DeliveryRead(
        id=item.id,
        sequence=item.delivery_number,
        over_number=item.over_number,
        ball_number=item.ball_number,
        striker=PlayerSummary.model_validate(item.striker),
        non_striker=PlayerSummary.model_validate(item.non_striker),
        bowler=PlayerSummary.model_validate(item.bowler),
        batter_runs=item.batter_runs,
        extra_runs=item.extra_runs,
        total_runs=item.total_runs,
        is_legal_ball=item.is_legal_ball,
        recorded_at=item.recorded_at,
    )


async def _state_response(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
) -> ScoringStateRead:

    deliveries = await repository.get_recorded_deliveries(innings.id)
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

    if innings.current_bowler_id is None:
        raise ValidationError(
            "Current bowler "
            "is not configured"
        )

    bowler = (
        await _player_or_error(
            repository,
            innings
            .current_bowler_id,
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

    next_sequence = await repository.next_delivery_number(innings.id)
    recent = deliveries[-12:]

    cache_matches_history = (
        innings.total_runs
        == derived.total_runs
        and innings.legal_balls
        == derived.legal_balls
        and innings.striker_id
        == derived.striker_id
        and innings.non_striker_id
        == derived.non_striker_id
    )

    # ======================
    # INNINGS LIFECYCLE
    # ======================
    innings_list = await repository.list_innings(match.id)
    totals = await repository.delivery_totals(match.id)
    chase = _chase_state(match, innings, innings_list, totals)
    innings_complete = _innings_finished(match, innings, derived.legal_balls, chase)
    match_over = match.status in {MatchStatus.COMPLETED, MatchStatus.ABANDONED}
    has_next_innings = innings.innings_number < max_innings(match.innings_per_team)

    can_start_next_innings = innings_complete and has_next_innings and not match_over

    at_over_boundary = (
        derived.legal_balls > 0
        and derived.legal_balls % match.balls_per_over == 0
        and not innings_complete
    )
    previous_bowler = (
        previous_over_bowler_id(deliveries)
        if at_over_boundary
        else None
    )

    target = runs_required = balls_remaining = None
    if chase is not None:
        target = chase.target
        runs_required = max(target - derived.total_runs, 0)
        if match.total_overs is not None:
            balls_remaining = max(
                match.total_overs * match.balls_per_over - derived.legal_balls,
                0,
            )

    summary = None
    if chase is not None and (innings_complete or match.status == MatchStatus.COMPLETED):
        summary = result_summary(
            batting_team_name=innings.batting_team.name,
            bowling_team_name=innings.bowling_team.name,
            batting_runs=chase.batting_runs,
            bowling_runs=chase.bowling_runs,
            wickets=innings.wickets,
            players_per_side=match.players_per_side,
        )

    return ScoringStateRead(
        match_id=match.id,
        innings_id=innings.id,
        innings_number=innings.innings_number,
        match_status=match.status,
        innings_status=innings.status,
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
        total_runs= derived.total_runs,
        wickets=innings.wickets,
        legal_balls=derived.legal_balls,
        completed_overs=completed_overs,
        balls_in_current_over=balls_in_over,
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
        total_overs=match.total_overs,
        balls_per_over=match.balls_per_over,
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

        next_sequence=(
            next_sequence
        ),

        next_over_number=(
            next_over
        ),

        next_ball_number=(
            next_ball
        ),

        at_over_boundary=at_over_boundary,

        bowler_change_required=bowler_change_required(
            legal_balls=derived.legal_balls,
            balls_per_over=match.balls_per_over,
            previous_bowler_id=previous_bowler,
            current_bowler_id=innings.current_bowler_id,
        ) if at_over_boundary else False,

        previous_over_bowler_id=previous_bowler,

        recent_deliveries=[
            _delivery_read(item)
            for item
            in recent
        ],

        innings=[
            InningsSummary(
                innings_number=item.innings_number,
                status=item.status,
                batting_team=TeamSummary.model_validate(item.batting_team),
                total_runs=totals.get(item.id, (0, 0))[0],
                wickets=item.wickets,
                legal_balls=totals.get(item.id, (0, 0))[1],
                overs=overs_display(
                    totals.get(item.id, (0, 0))[1],
                    match.balls_per_over,
                ),
            )
            for item in innings_list
        ],
        innings_complete=innings_complete,
        can_end_innings=(
            match.total_overs is None
            and not innings_complete
            and not match_over
            and derived.legal_balls > 0
        ),
        can_start_next_innings=can_start_next_innings,
        next_innings_number=(
            innings.innings_number + 1
            if can_start_next_innings
            else None
        ),
        # Sides alternate: the bowling
        # side bats next.
        next_batting_team=(
            TeamSummary.model_validate(innings.bowling_team)
            if can_start_next_innings
            else None
        ),
        next_bowling_team=(
            TeamSummary.model_validate(innings.batting_team)
            if can_start_next_innings
            else None
        ),
        target=target,
        runs_required=runs_required,
        balls_remaining=balls_remaining,
        result_summary=summary,

        cache_matches_history=(
            cache_matches_history
        ),
    )


async def _current_state(repository: ScoringRepository, match_id: UUID, after: str) -> ScoringStateRead:
    # Transaction is committed
    # before state is returned.
    match = await repository.get_match(match_id)
    innings = await repository.get_current_innings(match_id)

    if match is None or innings is None:
        raise NotFoundError(f"Scoring state not found after {after}")

    return await _state_response(repository, match=match, innings=innings)


async def get_scoring_state(session: AsyncSession, match_id: UUID) -> ScoringStateRead:
    repository = ScoringRepository(session)
    match = await repository.get_match(match_id)

    if match is None:
        raise NotFoundError("Match not found")

    if match.status == MatchStatus.DRAFT:
        raise ConflictError(
            "Complete the match setup "
            "before live scoring"
        )

    innings = await repository.get_current_innings(match_id)

    if innings is None:
        raise NotFoundError(
            "First innings has "
            "not been configured"
        )

    # Reading is allowed during innings
    # breaks and after the match ends;
    # only writes need a scoreable innings.
    return await _state_response(repository, match=match, innings=innings)


async def record_delivery(session: AsyncSession, match_id: UUID, payload: DeliveryCreate) -> ScoringStateRead:
    repository = ScoringRepository(session)

    try:

        async with service_transaction(session):
            # ======================
            # CONCURRENCY BOUNDARY
            # ======================
            #
            # Scorer A and Scorer B
            # cannot calculate the
            # next sequence at the
            # same time for the same
            # innings.
            innings = await repository.lock_current_innings(match_id)

            if innings is None:
                raise NotFoundError(
                    "First innings has "
                    "not been configured"
                )

            match = await repository.get_match(match_id)

            if match is None:
                raise NotFoundError("Match not found")

            _ensure_scoreable(match, innings)
            deliveries = await repository.get_recorded_deliveries_plain(innings.id)
            before = (
                rebuild_from_deliveries(
                    innings,
                    deliveries,
                    balls_per_over=(
                        match.balls_per_over
                    ),
                )
            )
            if _overs_complete(match, before.legal_balls):
                raise ConflictError(
                    "The configured "
                    "over limit has "
                    "been reached for "
                    "this innings"
                )

            if innings.current_bowler_id is None:
                raise ValidationError(
                    "Current bowler "
                    "is not configured"
                )

            if bowler_change_required(
                legal_balls=before.legal_balls,
                balls_per_over=match.balls_per_over,
                previous_bowler_id=previous_over_bowler_id(deliveries),
                current_bowler_id=innings.current_bowler_id,
            ):
                raise ConflictError(
                    "Over complete. Select "
                    "a different bowler "
                    "for the next over"
                )

            (
                over_number,
                ball_number,
            ) = ball_position(
                before.legal_balls,
                match.balls_per_over
            )
            sequence = await repository.next_delivery_number(innings.id)
            delivery = Delivery(
                match_id=match.id,
                innings_id=innings.id,
                delivery_number=sequence,
                over_number=over_number,
                ball_number=ball_number,
                striker_id=before.striker_id,
                non_striker_id=before.non_striker_id,
                bowler_id=innings.current_bowler_id,
                batter_runs=payload.runs,
                # Extras come in Stage 5.
                extra_runs=0,
                total_runs=payload.runs,
                # Every Stage 4 event
                # is a legal ball.
                is_legal_ball=True,
                status=DeliveryStatus.RECORDED,
                actor_id=None,
            )
            session.add(delivery)
            await session.flush()
            (
                after_striker,
                after_non_striker,
            ) = advance_batters(
                before.striker_id,
                before
                .non_striker_id,
                runs=(
                    payload.runs
                ),
                legal_balls_after=(
                    before.legal_balls
                    + 1
                ),
                balls_per_over=match.balls_per_over)

            # These values are only
            # caches.
            #
            # The Delivery history
            # remains authoritative.
            innings.total_runs = before.total_runs + payload.runs
            innings.legal_balls = before.legal_balls + 1
            innings.striker_id = after_striker
            innings.non_striker_id = after_non_striker
            innings.status = InningsStatus.LIVE

            # First official delivery
            # starts the match.
            if match.status == MatchStatus.READY:
                match.status = MatchStatus.LIVE

            # Over limit reached or target
            # chased down: close the innings
            # in the same transaction.
            innings_list = await repository.list_innings(match.id)
            totals = await repository.delivery_totals(match.id)
            chase = _chase_state(match, innings, innings_list, totals)

            if _innings_finished(match, innings, innings.legal_balls, chase):
                _close_innings(match, innings)

            add_audit_log(
                session,
                entity_type="delivery",
                entity_id=delivery.id,
                action=AuditAction.CREATED,
                details={
                    "match_id":
                        str(match.id),
                    "innings_id":
                        str(innings.id),
                    "sequence":
                        sequence,
                    "over_number":
                        over_number,
                    "ball_number":
                        ball_number,
                    "runs":
                        payload.runs,
                },
            )

            await session.flush()

        return await _current_state(repository, match_id, "delivery commit")

    except IntegrityError as error:
        # Secondary concurrency guard:
        #
        # UNIQUE
        # (innings_id, delivery_number)
        raise integrity_conflict(error, "Delivery") from error


async def change_bowler(session: AsyncSession, match_id: UUID, payload: BowlerChange) -> ScoringStateRead:
    repository = ScoringRepository(session)
    async with service_transaction(session):
        innings = await repository.lock_current_innings(match_id)
        if innings is None:
            raise NotFoundError(
                "First innings has "
                "not been configured"
            )

        match = await repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")

        _ensure_scoreable(match, innings)
        deliveries = await repository.get_recorded_deliveries_plain(innings.id)

        derived = (
            rebuild_from_deliveries(
                innings,
                deliveries,

                balls_per_over=(
                    match.balls_per_over
                ),
            )
        )

        # Opening bowler comes from
        # match / innings setup.
        if derived.legal_balls == 0:
            raise ConflictError(
                "The opening bowler "
                "is already configured "
                "for this innings"
            )

        # Never switch a bowler
        # midway through an over.
        if derived.legal_balls % match.balls_per_over != 0:
            raise ConflictError(
                "Bowler can only "
                "be changed at an "
                "over boundary"
            )

        if _overs_complete(match, derived.legal_balls):
            raise ConflictError(
                "The configured "
                "over limit has "
                "been reached"
            )

        # No bowler bowls two
        # consecutive overs.
        if payload.bowler_id == previous_over_bowler_id(deliveries):
            raise ValidationError(
                "This bowler bowled the "
                "previous over. Choose a "
                "different bowler"
            )

        belongs = (
            await repository
            .is_playing_team_player(
                match_id=match.id,
                team_id=innings.bowling_team_id,
                player_id=payload.bowler_id,
            )
        )

        if not belongs:
            raise ValidationError(
                "Bowler must belong "
                "to the bowling "
                "team's selected "
                "playing team"
            )

        player = await repository.get_player(payload.bowler_id)
        if player is None:
            raise NotFoundError("Bowler not found")

        innings.current_bowler_id = payload.bowler_id
        add_audit_log(
            session,
            entity_type="innings",
            entity_id=innings.id,
            action=AuditAction.UPDATED,
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

    return await _current_state(repository, match_id, "bowler change")


async def end_innings(session: AsyncSession, match_id: UUID) -> ScoringStateRead:
    """
    Manual close for unlimited-overs
    matches. Limited-overs innings close
    automatically at the over limit.
    """

    repository = ScoringRepository(session)
    async with service_transaction(session):
        innings = await repository.lock_current_innings(match_id)
        if innings is None:
            raise NotFoundError(
                "First innings has "
                "not been configured"
            )

        match = await repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")

        _ensure_scoreable(match, innings)

        if match.total_overs is not None:
            raise ConflictError(
                "Limited-overs innings end "
                "automatically when the "
                "over limit is reached"
            )

        deliveries = await repository.get_recorded_deliveries_plain(innings.id)
        if not deliveries:
            raise ConflictError(
                "Record at least one "
                "delivery before ending "
                "the innings"
            )

        _close_innings(match, innings)
        add_audit_log(
            session,
            entity_type="innings",
            entity_id=innings.id,
            action=AuditAction.UPDATED,
            details={
                "setup": "innings_ended",
                "innings_number": innings.innings_number,
            },
        )

        await session.flush()

    return await _current_state(repository, match_id, "ending the innings")


async def start_next_innings(session: AsyncSession, match_id: UUID, payload: NextInningsCreate) -> ScoringStateRead:
    repository = ScoringRepository(session)

    try:

        async with service_transaction(session):
            # Same lock as scoring: a late
            # delivery and a new innings can
            # never interleave.
            previous = await repository.lock_current_innings(match_id)
            if previous is None:
                raise NotFoundError(
                    "First innings has "
                    "not been configured"
                )

            match = await repository.get_match(match_id)
            if match is None:
                raise NotFoundError("Match not found")

            if match.status in {MatchStatus.COMPLETED, MatchStatus.ABANDONED}:
                raise ConflictError("The match is already finished")

            next_number = previous.innings_number + 1
            if next_number > max_innings(match.innings_per_team):
                raise ConflictError(
                    "All innings for this "
                    "match have been played"
                )

            deliveries = await repository.get_recorded_deliveries_plain(previous.id)
            legal_balls = sum(1 for item in deliveries if item.is_legal_ball)

            # Innings 1 cannot be the final
            # innings, so no chase applies.
            if not _innings_finished(match, previous, legal_balls, None):
                raise ConflictError(
                    f"Innings {previous.innings_number} "
                    "is still in progress"
                )

            # Sides alternate.
            batting_team_id = previous.bowling_team_id
            bowling_team_id = previous.batting_team_id

            for player_id, team_id, label in (
                (payload.striker_id, batting_team_id, "Striker"),
                (payload.non_striker_id, batting_team_id, "Non-striker"),
                (payload.opening_bowler_id, bowling_team_id, "Opening bowler"),
            ):
                side = "batting" if team_id == batting_team_id else "bowling"
                if not await repository.is_playing_team_player(
                    match_id=match.id,
                    team_id=team_id,
                    player_id=player_id,
                ):
                    raise ValidationError(
                        f"{label} must belong "
                        f"to the {side} team's "
                        "playing team"
                    )

            # Heals innings that reached the
            # over limit before auto-close
            # existed.
            previous.status = InningsStatus.COMPLETED

            innings = Innings(
                match_id=match.id,
                innings_number=next_number,
                batting_team_id=batting_team_id,
                bowling_team_id=bowling_team_id,
                status=InningsStatus.PENDING,
                striker_id=payload.striker_id,
                non_striker_id=payload.non_striker_id,
                current_bowler_id=payload.opening_bowler_id,
            )
            session.add(innings)
            match.status = MatchStatus.LIVE
            await session.flush()

            add_audit_log(
                session,
                entity_type="innings",
                entity_id=innings.id,
                action=AuditAction.CREATED,
                details={
                    "setup": "next_innings",
                    "innings_number": next_number,
                    "striker_id": str(payload.striker_id),
                    "non_striker_id": str(payload.non_striker_id),
                    "opening_bowler_id": str(payload.opening_bowler_id),
                },
            )

            await session.flush()

        return await _current_state(repository, match_id, "starting the innings")

    except IntegrityError as error:
        # UNIQUE (match_id, innings_number)
        # stops a double start.
        raise integrity_conflict(error, "Innings") from error
