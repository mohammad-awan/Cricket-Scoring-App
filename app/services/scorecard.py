from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.exceptions import (
    NotFoundError,
)

from app.models import (
    Innings,
    Match,
)

from app.models.enums import (
    InningsStatus,
    MatchStatus,
)

from app.repositories.scorecard import (
    DeliveryScoreRow,
    MatchPlayerRow,
    ScorecardRepository,
)

from app.schemas.match_setup import (
    PlayerSummary,
    TeamSummary,
)

from app.schemas.scorecard import (
    BattingScorecardRow,
    BowlingScorecardRow,
    ChaseRead,
    ExtrasRead,
    FullScorecardRead,
    InningsScorecardRead,
    MatchLifecycleRead,
    MatchResultRead,
    PartnershipRead,
)


BOWLER_WICKET_TYPES = {
    "bowled",
    "caught",
    "lbw",
    "stumped",
    "hit_wicket",
}


@dataclass(
    frozen=True
)
class InningsTotals:

    runs: int

    wickets: int

    legal_balls: int


def overs_display(
    legal_balls: int,
    balls_per_over: int,
) -> str:

    completed, balls = divmod(
        legal_balls,
        balls_per_over,
    )

    return (
        f"{completed}."
        f"{balls}"
    )


def run_rate(
    runs: int,
    legal_balls: int,
    balls_per_over: int,
) -> float:

    if legal_balls <= 0:

        return 0.0

    overs = (
        legal_balls
        / balls_per_over
    )

    return round(
        runs
        / overs,
        2,
    )


def strike_rate(
    runs: int,
    balls: int,
) -> float:

    if balls <= 0:

        return 0.0

    return round(
        (
            runs
            * 100
        )
        / balls,
        2,
    )


def economy_rate(
    runs: int,
    legal_balls: int,
    balls_per_over: int,
) -> float:

    if legal_balls <= 0:

        return 0.0

    overs = (
        legal_balls
        / balls_per_over
    )

    return round(
        runs
        / overs,
        2,
    )


def required_run_rate(
    runs_required: (
        int | None
    ),
    balls_remaining: (
        int | None
    ),
    balls_per_over: int,
) -> float | None:

    if (
        runs_required is None
        or balls_remaining is None
    ):

        return None

    if runs_required <= 0:

        return 0.0

    if balls_remaining <= 0:

        return None

    overs_remaining = (
        balls_remaining
        / balls_per_over
    )

    return round(
        runs_required
        / overs_remaining,
        2,
    )


def player_summary(
    player_id: UUID,
    full_name: str,
    short_name: (
        str | None
    ),
) -> PlayerSummary:

    return PlayerSummary(
        id=player_id,

        full_name=(
            full_name
        ),

        short_name=(
            short_name
        ),
    )


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


def innings_totals(
    deliveries: list[
        DeliveryScoreRow
    ],
) -> InningsTotals:

    return InningsTotals(
        runs=sum(
            item.total_runs

            for item
            in deliveries
        ),

        wickets=sum(
            1

            for item
            in deliveries

            if (
                item
                .dismissed_player_id
                is not None
            )
        ),

        legal_balls=sum(
            1

            for item
            in deliveries

            if item.is_legal_ball
        ),
    )


def batting_scorecard(
    *,
    players: list[
        MatchPlayerRow
    ],
    deliveries: list[
        DeliveryScoreRow
    ],
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

        if (
            dismissal
            is not None
        ):

            dismissal_label = (
                dismissal
            )

            is_not_out = False

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


def bowling_scorecard(
    *,
    deliveries: list[
        DeliveryScoreRow
    ],
    balls_per_over: int,
) -> list[
    BowlingScorecardRow
]:

    names: dict[
        UUID,
        tuple[
            str,
            str | None,
        ],
    ] = {}

    legal_balls: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    runs_conceded: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    wickets: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    wides: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    no_balls: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    over_legal: dict[
        tuple[
            UUID,
            int,
        ],
        int,
    ] = defaultdict(
        int
    )

    over_runs: dict[
        tuple[
            UUID,
            int,
        ],
        int,
    ] = defaultdict(
        int
    )

    for item in deliveries:

        names[
            item.bowler_id
        ] = (
            item.bowler_name,
            item.bowler_short_name,
        )

        if item.is_legal_ball:

            legal_balls[
                item.bowler_id
            ] += 1

            over_legal[
                (
                    item.bowler_id,
                    item.over_number,
                )
            ] += 1

        # Byes and leg byes are
        # not charged to bowler.
        conceded = (
            item.batter_runs
            + item.wide_runs
            + item.no_ball_runs
        )

        runs_conceded[
            item.bowler_id
        ] += conceded

        over_runs[
            (
                item.bowler_id,
                item.over_number,
            )
        ] += conceded

        wides[
            item.bowler_id
        ] += (
            item.wide_runs
        )

        no_balls[
            item.bowler_id
        ] += (
            item.no_ball_runs
        )

        if (
            item.wicket_type
            in BOWLER_WICKET_TYPES
        ):

            wickets[
                item.bowler_id
            ] += 1

    maidens: dict[
        UUID,
        int,
    ] = defaultdict(
        int
    )

    for (
        key,
        legal_count,
    ) in over_legal.items():

        bowler_id, _ = key

        if (
            legal_count
            == balls_per_over

            and over_runs[
                key
            ] == 0
        ):

            maidens[
                bowler_id
            ] += 1

    result: list[
        BowlingScorecardRow
    ] = []

    for (
        bowler_id,
        (
            full_name,
            short_name,
        ),
    ) in names.items():

        bowler_balls = (
            legal_balls[
                bowler_id
            ]
        )

        bowler_runs = (
            runs_conceded[
                bowler_id
            ]
        )

        result.append(
            BowlingScorecardRow(
                player=(
                    player_summary(
                        bowler_id,
                        full_name,
                        short_name,
                    )
                ),

                overs=(
                    overs_display(
                        bowler_balls,
                        balls_per_over,
                    )
                ),

                legal_balls=(
                    bowler_balls
                ),

                maidens=(
                    maidens[
                        bowler_id
                    ]
                ),

                runs_conceded=(
                    bowler_runs
                ),

                wickets=(
                    wickets[
                        bowler_id
                    ]
                ),

                wides=(
                    wides[
                        bowler_id
                    ]
                ),

                no_balls=(
                    no_balls[
                        bowler_id
                    ]
                ),

                economy=(
                    economy_rate(
                        bowler_runs,
                        bowler_balls,
                        balls_per_over,
                    )
                ),
            )
        )

    result.sort(
        key=lambda row: (
            -row.legal_balls,
            row.player.full_name,
        )
    )

    return result


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


def extras_summary(
    deliveries: list[
        DeliveryScoreRow
    ],
) -> ExtrasRead:

    wides = sum(
        item.wide_runs

        for item
        in deliveries
    )

    no_balls = sum(
        item.no_ball_runs

        for item
        in deliveries
    )

    byes = sum(
        item.bye_runs

        for item
        in deliveries
    )

    leg_byes = sum(
        item.leg_bye_runs

        for item
        in deliveries
    )

    return ExtrasRead(
        total=(
            wides
            + no_balls
            + byes
            + leg_byes
        ),

        wides=wides,

        no_balls=no_balls,

        byes=byes,

        leg_byes=leg_byes,
    )


def result_summary(
    match: Match,
) -> str | None:

    if (
        match.result_type
        is None
    ):

        return None

    if (
        match.result_type
        == "tie"
    ):

        return "Match tied"

    winner = (
        match.winner_team
    )

    if winner is None:

        return None

    margin = (
        match.result_margin
        or 0
    )

    if (
        match.result_type
        == "runs"
    ):

        unit = (
            "run"
            if margin == 1
            else "runs"
        )

    else:

        unit = (
            "wicket"
            if margin == 1
            else "wickets"
        )

    return (
        f"{winner.name} "
        f"won by "
        f"{margin} "
        f"{unit}"
    )


def state_label(
    match: Match,
    innings: (
        Innings | None
    ),
) -> str:

    if (
        match.status
        == MatchStatus.DRAFT
    ):

        return "Draft"

    if (
        match.status
        == MatchStatus.READY
    ):

        return "Ready"

    if (
        match.status
        == MatchStatus.INNINGS_BREAK
    ):

        return (
            "Innings Break"
        )

    if (
        match.status
        == MatchStatus.COMPLETED
    ):

        return "Completed"

    if (
        match.status
        == MatchStatus.ABANDONED
    ):

        return "Abandoned"

    if innings is None:

        return "Live"

    return (
        f"Innings "
        f"{innings.innings_number} "
        f"Live"
    )


def team_prior_runs(
    *,
    innings_cards: list[
        InningsScorecardRead
    ],
    team_id: UUID,
    before_innings_number: int,
) -> int:

    return sum(
        card.total_runs

        for card
        in innings_cards

        if (
            card
            .batting_team
            .id
            == team_id

            and card
            .innings_number
            < before_innings_number
        )
    )


def chase_metrics(
    *,
    match: Match,
    innings_cards: list[
        InningsScorecardRead
    ],
    current: (
        InningsScorecardRead
        | None
    ),
) -> ChaseRead:

    if current is None:

        return ChaseRead(
            target=None,

            runs_required=None,

            balls_remaining=None,

            required_run_rate=None,
        )

    final_innings_number = (
        match.innings_per_team
        * 2
    )

    if (
        current.innings_number
        < final_innings_number
    ):

        return ChaseRead(
            target=None,

            runs_required=None,

            balls_remaining=None,

            required_run_rate=None,
        )

    batting_previous = (
        team_prior_runs(
            innings_cards=(
                innings_cards
            ),

            team_id=(
                current
                .batting_team
                .id
            ),

            before_innings_number=(
                current
                .innings_number
            ),
        )
    )

    bowling_total = (
        team_prior_runs(
            innings_cards=(
                innings_cards
            ),

            team_id=(
                current
                .bowling_team
                .id
            ),

            before_innings_number=(
                current
                .innings_number
                + 1
            ),
        )
    )

    target = (
        bowling_total
        - batting_previous
        + 1
    )

    runs_required = max(
        target
        - current.total_runs,
        0,
    )

    balls_remaining = None

    if (
        match.total_overs
        is not None
    ):

        balls_remaining = max(
            (
                match.total_overs
                * match.balls_per_over

                - current
                .legal_balls
            ),
            0,
        )

    return ChaseRead(
        target=target,

        runs_required=(
            runs_required
        ),

        balls_remaining=(
            balls_remaining
        ),

        required_run_rate=(
            required_run_rate(
                runs_required,
                balls_remaining,
                match.balls_per_over,
            )
        ),
    )


async def get_full_scorecard(
    session: AsyncSession,
    match_id: UUID,
) -> FullScorecardRead:

    repository = (
        ScorecardRepository(
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

    innings_list = (
        await repository
        .list_innings(
            match_id
        )
    )

    match_players = (
        await repository
        .list_match_players(
            match_id
        )
    )

    players_by_team: dict[
        UUID,
        list[
            MatchPlayerRow
        ],
    ] = defaultdict(
        list
    )

    for player in match_players:

        players_by_team[
            player.team_id
        ].append(
            player
        )

    innings_cards: list[
        InningsScorecardRead
    ] = []

    for innings in innings_list:

        deliveries = (
            await repository
            .list_delivery_rows(
                innings.id
            )
        )

        totals = (
            innings_totals(
                deliveries
            )
        )

        innings_cards.append(
            InningsScorecardRead(
                innings_id=(
                    innings.id
                ),

                innings_number=(
                    innings
                    .innings_number
                ),

                status=(
                    innings.status
                ),

                batting_team=(
                    TeamSummary
                    .model_validate(
                        innings
                        .batting_team
                    )
                ),

                bowling_team=(
                    TeamSummary
                    .model_validate(
                        innings
                        .bowling_team
                    )
                ),

                total_runs=(
                    totals.runs
                ),

                wickets=(
                    totals.wickets
                ),

                legal_balls=(
                    totals.legal_balls
                ),

                overs=(
                    overs_display(
                        totals
                        .legal_balls,

                        match
                        .balls_per_over,
                    )
                ),

                run_rate=(
                    run_rate(
                        totals.runs,

                        totals
                        .legal_balls,

                        match
                        .balls_per_over,
                    )
                ),

                extras=(
                    extras_summary(
                        deliveries
                    )
                ),

                batting=(
                    batting_scorecard(
                        players=(
                            players_by_team[
                                innings
                                .batting_team_id
                            ]
                        ),

                        deliveries=(
                            deliveries
                        ),
                    )
                ),

                bowling=(
                    bowling_scorecard(
                        deliveries=(
                            deliveries
                        ),

                        balls_per_over=(
                            match
                            .balls_per_over
                        ),
                    )
                ),

                partnerships=(
                    partnership_scorecard(
                        deliveries
                    )
                ),
            )
        )

    current_innings = (
        innings_list[-1]

        if innings_list

        else None
    )

    current_card = (
        innings_cards[-1]

        if innings_cards

        else None
    )

    max_innings = (
        match.innings_per_team
        * 2
    )

    can_start_next = (
        current_innings
        is not None

        and current_innings.status
        == InningsStatus.COMPLETED

        and current_innings
        .innings_number
        < max_innings

        and match.status
        not in {
            MatchStatus.COMPLETED,
            MatchStatus.ABANDONED,
        }
    )

    can_score = (
        current_innings
        is not None

        and match.status
        in {
            MatchStatus.READY,
            MatchStatus.LIVE,
        }

        and current_innings.status
        in {
            InningsStatus.PENDING,
            InningsStatus.LIVE,
        }
    )

    winner_team = (
        TeamSummary
        .model_validate(
            match.winner_team
        )

        if (
            match.winner_team
            is not None
        )

        else None
    )

    lifecycle = (
        MatchLifecycleRead(
            match_id=(
                match.id
            ),

            status=(
                match.status
            ),

            current_innings_number=(
                current_innings
                .innings_number

                if (
                    current_innings
                    is not None
                )

                else None
            ),

            state_label=(
                state_label(
                    match,
                    current_innings,
                )
            ),

            can_score=(
                can_score
            ),

            can_start_next_innings=(
                can_start_next
            ),

            chase=(
                chase_metrics(
                    match=match,

                    innings_cards=(
                        innings_cards
                    ),

                    current=(
                        current_card
                    ),
                )
            ),

            result=(
                MatchResultRead(
                    completed=(
                        match.status
                        == MatchStatus
                        .COMPLETED
                    ),

                    winner_team=(
                        winner_team
                    ),

                    result_type=(
                        match
                        .result_type
                    ),

                    result_margin=(
                        match
                        .result_margin
                    ),

                    summary=(
                        result_summary(
                            match
                        )
                    ),

                    completed_at=(
                        match
                        .completed_at
                    ),
                )
            ),
        )
    )

    return FullScorecardRead(
        match_id=(
            match.id
        ),

        title=(
            match.title
        ),

        status=(
            match.status
        ),

        team_a=(
            TeamSummary
            .model_validate(
                match.team_a
            )
        ),

        team_b=(
            TeamSummary
            .model_validate(
                match.team_b
            )
        ),

        total_overs=(
            match.total_overs
        ),

        balls_per_over=(
            match.balls_per_over
        ),

        innings_per_team=(
            match.innings_per_team
        ),

        innings=(
            innings_cards
        ),

        lifecycle=(
            lifecycle
        ),
    )
