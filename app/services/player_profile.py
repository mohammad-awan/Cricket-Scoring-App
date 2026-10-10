from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import ceil
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError
from app.models import (
    BattingHand,
    BowlingArm,
    BowlingStyle,
    Player,
    WicketType,
)
from app.repositories.players import PlayerRepository
from app.repositories.player_profile import (
    MatchSelectionRow,
    PlayerActivityRow,
    PlayerProfileRepository,
)
# 03156497010

from app.schemas.player_profile import (
    BattingCareerRead,
    BowlingCareerRead,
    MatchBattingFigureRead,
    MatchBowlingFigureRead,
    PlayerCareerRead,
    PlayerIdentityRead,
    PlayerMatchHistoryPageRead,
    PlayerMatchHistoryRead,
    PlayerProfileRead,
    PlayerTeamMembershipRead,
    RecentBattingInningsRead,
    RecentBowlingInningsRead,
)


BOWLER_WICKET_TYPES = {
    WicketType.BOWLED,
    WicketType.CAUGHT,
    WicketType.LBW,
    WicketType.STUMPED,
    WicketType.HIT_WICKET,
}


def calculate_age(date_of_birth: date | None, *, today: date | None = None) -> int | None:
    if date_of_birth is None:
        return None

    current = today or date.today()

    return (
        current.year
        - date_of_birth.year
        - ((current.month, current.day) < (date_of_birth.month, date_of_birth.day))
    )


def batting_style_display(hand: BattingHand | None) -> str | None:
    if hand is BattingHand.RIGHT:
        return "Right-hand batter"

    if hand is BattingHand.LEFT:
        return "Left-hand batter"

    return None


def bowling_style_display(arm: BowlingArm | None, style: BowlingStyle | None) -> str | None:
    if arm is BowlingArm.NONE:
        return "Does not bowl"

    if arm is None:
        return None

    arm_label = "Right-arm" if arm is BowlingArm.RIGHT else "Left-arm"

    if style is None:
        return arm_label

    style_labels = {
        BowlingStyle.FAST: "fast",
        BowlingStyle.FAST_MEDIUM: "fast-medium",
        BowlingStyle.MEDIUM_FAST: "medium-fast",
        BowlingStyle.MEDIUM: "medium",
        BowlingStyle.OFF_BREAK: "off break",
        BowlingStyle.LEG_BREAK: "leg break",
        BowlingStyle.ORTHODOX: "orthodox",
        BowlingStyle.WRIST_SPIN: "wrist spin",
        BowlingStyle.MYSTERY_SPIN: "mystery spin",
        BowlingStyle.OTHER: "other",
    }

    return f"{arm_label} {style_labels[style]}"


def round_stat(value: float | None) -> float | None:
    if value is None:
        return None

    return round(value, 2)


def row_sort_key(row: PlayerActivityRow) -> tuple:
    return (row.scheduled_at or row.match_created_at, row.innings_number)


def build_batting(
    player_id: UUID,
    rows: list[
        PlayerActivityRow
    ],
) -> tuple[
    BattingCareerRead,
    dict[
        tuple[UUID, UUID],
        MatchBattingFigureRead,
    ],
]:

    innings_rows: dict[tuple[UUID, UUID], list[PlayerActivityRow]] = defaultdict(list)

    for row in rows:
        if row.striker_id == player_id or row.dismissed_player_id == player_id:
            innings_rows[(row.match_id, row.innings_id)].append(row)

    figures: dict[tuple[UUID, UUID], MatchBattingFigureRead] = {}
    metadata: dict[tuple[UUID, UUID], PlayerActivityRow] = {}

    for key, group in innings_rows.items():
        first = group[0]
        metadata[key] = first
        striker_rows = [row for row in group if row.striker_id == player_id]
        runs = sum(row.batter_runs for row in striker_rows)

        # Wides are not balls faced.
        balls_faced = sum(1 for row in striker_rows if row.wide_runs == 0)
        fours = sum(1 for row in striker_rows if row.batter_runs == 4)
        sixes = sum(1 for row in striker_rows if row.batter_runs == 6)
        dismissed = any(row.dismissed_player_id == player_id for row in group)

        figures[key] = MatchBattingFigureRead(
            innings_id=first.innings_id,
            innings_number=first.innings_number,
            runs=runs,
            balls_faced=balls_faced,
            fours=fours,
            sixes=sixes,
            not_out=not dismissed,
        )

    values = list(figures.values())
    total_runs = sum(item.runs for item in values)
    total_balls = sum(item.balls_faced for item in values)
    dismissals = sum(1 for item in values if not item.not_out)
    innings_count = len(values)
    matches = len({key[0] for key in figures})
    highest_score = max((item.runs for item in values), default=0)

    highest_score_not_out = (
        any(item.runs == highest_score and item.not_out for item in values)
        if values
        else False
    )

    ordered_keys = sorted(
        figures,
        key=lambda key: row_sort_key(metadata[key]),
        reverse=True,
    )

    recent_form = [
        RecentBattingInningsRead(
            match_id=key[0],
            innings_id=key[1],
            innings_number=figures[key].innings_number,
            runs=figures[key].runs,
            balls_faced=figures[key].balls_faced,
            not_out=figures[key].not_out,
        )

        for key
        in ordered_keys[:5]
    ]

    career = BattingCareerRead(
        matches=matches,
        innings=innings_count,
        runs=total_runs,
        balls_faced=total_balls,
        not_outs=innings_count - dismissals,
        dismissals=dismissals,
        highest_score=highest_score,
        highest_score_not_out=highest_score_not_out,
        average=round_stat(total_runs / dismissals) if dismissals else None,
        strike_rate=round_stat((total_runs * 100) / total_balls) if total_balls else None,
        fours=sum(item.fours for item in values),
        sixes=sum(item.sixes for item in values),
        recent_form=recent_form,
    )

    return career, figures


def build_bowling(
    player_id: UUID,
    rows: list[
        PlayerActivityRow
    ],
) -> tuple[
    BowlingCareerRead,
    dict[
        tuple[UUID, UUID],
        MatchBowlingFigureRead,
    ],
]:

    innings_rows: dict[tuple[UUID, UUID], list[PlayerActivityRow]] = defaultdict(list)

    for row in rows:
        if row.bowler_id == player_id:
            innings_rows[(row.match_id, row.innings_id)].append(row)

    figures: dict[tuple[UUID, UUID], MatchBowlingFigureRead] = {}
    metadata: dict[tuple[UUID, UUID], PlayerActivityRow] = {}

    for key, group in innings_rows.items():
        first = group[0]
        metadata[key] = first
        legal_balls = sum(1 for row in group if row.is_legal_ball)

        # Byes and leg byes are not charged to the bowler.
        runs_conceded = sum(
            row.batter_runs + row.wide_runs + row.no_ball_runs
            for row in group
        )

        wickets = sum(
            1
            for row in group
            if row.wicket_type in BOWLER_WICKET_TYPES and row.dismissed_player_id is not None
        )

        overs = legal_balls / first.balls_per_over if first.balls_per_over else 0.0

        figures[key] = MatchBowlingFigureRead(
            innings_id=first.innings_id,
            innings_number=first.innings_number,
            balls_bowled=legal_balls,
            overs=round(overs, 2),
            runs_conceded=runs_conceded,
            wickets=wickets,
            economy=round_stat(runs_conceded / overs) if overs else None,
        )

    values = list(figures.values())
    total_balls = sum(item.balls_bowled for item in values)
    total_runs = sum(item.runs_conceded for item in values)
    total_wickets = sum(item.wickets for item in values)
    total_overs = sum(item.overs for item in values)
    best = None

    if values:
        best = sorted(values, key=lambda item: (-item.wickets, item.runs_conceded))[0]

    ordered_keys = sorted(
        figures,
        key=lambda key: row_sort_key(metadata[key]),
        reverse=True,
    )

    recent_form = [
        RecentBowlingInningsRead(
            match_id=key[0],
            innings_id=key[1],
            innings_number=figures[key].innings_number,
            wickets=figures[key].wickets,
            runs_conceded=figures[key].runs_conceded,
            balls_bowled=figures[key].balls_bowled,
        )

        for key
        in ordered_keys[:5]
    ]

    career = BowlingCareerRead(
        matches=len({key[0] for key in figures}),
        innings=len(values),
        balls_bowled=total_balls,
        overs=round(total_overs, 2),
        runs_conceded=total_runs,
        wickets=total_wickets,
        economy=round_stat(total_runs / total_overs) if total_overs else None,
        average=round_stat(total_runs / total_wickets) if total_wickets else None,
        strike_rate=round_stat(total_balls / total_wickets) if total_wickets else None,
        best_wickets=best.wickets if best else 0,
        best_runs=best.runs_conceded if best else 0,
        best_figures=f"{best.wickets}/{best.runs_conceded}" if best else None,
        recent_form=recent_form,
    )

    return career, figures


def history_items(
    selections: list[
        MatchSelectionRow
    ],
    batting_figures: dict[
        tuple[UUID, UUID],
        MatchBattingFigureRead,
    ],
    bowling_figures: dict[
        tuple[UUID, UUID],
        MatchBowlingFigureRead,
    ],
) -> list[
    PlayerMatchHistoryRead
]:

    result: list[PlayerMatchHistoryRead] = []

    for selection in selections:
        if selection.player_team_id == selection.team_a_id:
            player_team_id = selection.team_a_id
            player_team_name = selection.team_a_name
            opponent_team_id = selection.team_b_id
            opponent_team_name = selection.team_b_name

        else:
            player_team_id = selection.team_b_id
            player_team_name = selection.team_b_name
            opponent_team_id = selection.team_a_id
            opponent_team_name = selection.team_a_name

        batting = sorted(
            [
                figure

                for (
                    match_id,
                    _,
                ), figure
                in batting_figures.items()
                if match_id == selection.match_id
            ],
            key=lambda item: item.innings_number,
        )

        bowling = sorted(
            [
                figure
                for (
                    match_id,
                    _,
                ), figure
                in bowling_figures.items()
                if match_id == selection.match_id
            ],
            key=lambda item: item.innings_number
        )

        result.append(
            PlayerMatchHistoryRead(
                match_id=selection.match_id,
                title=selection.title,
                match_date=selection.scheduled_at or selection.match_created_at,
                scheduled_at=selection.scheduled_at,
                player_team_id=player_team_id,
                player_team_name=player_team_name,
                opponent_team_id=opponent_team_id,
                opponent_team_name=opponent_team_name,
                batting=batting,
                bowling=bowling,
            )
        )

    return result


async def require_player(session: AsyncSession, player_id: UUID) -> Player:
    player = await PlayerRepository(session).get_by_id(player_id)

    if player is None:
        raise NotFoundError("Player not found")

    return player


async def get_player_match_history(
    session: AsyncSession,
    player_id: UUID,
    *,
    page: int = 1,
    page_size: int = 10,
) -> PlayerMatchHistoryPageRead:
    
    await require_player(session, player_id)
    repository = PlayerProfileRepository(session)
    selections = await (
        repository
        .match_history_page(
            player_id,
            page=page,
            page_size=page_size,
        )
    )
    total = await repository.match_history_count(player_id)
    match_ids = [item.match_id for item in selections]

    activity = await (
        repository
        .activity_rows(
            player_id,
            match_ids=match_ids,
        )
    )

    (
        _,
        batting_figures,
    ) = build_batting(
        player_id,
        activity,
    )

    (
        _,
        bowling_figures,
    ) = build_bowling(
        player_id,
        activity,
    )

    return PlayerMatchHistoryPageRead(
        items=history_items(
            selections,
            batting_figures,
            bowling_figures,
        ),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0
    )


async def get_player_profile(session: AsyncSession, player_id: UUID) -> PlayerProfileRead:
    player = await require_player(session, player_id)
    repository = PlayerProfileRepository(session)
    activity = await repository.activity_rows(player_id)

    (
        batting,
        batting_figures,
    ) = build_batting(
        player_id,
        activity,
    )

    (
        bowling,
        bowling_figures,
    ) = build_bowling(
        player_id,
        activity,
    )

    memberships = await repository.active_team_memberships(player_id)
    recent_selections = await repository.match_history_page(player_id, page=1, page_size=5)

    return PlayerProfileRead(
        player=PlayerIdentityRead(
            id=player.id,
            full_name=player.full_name,
            short_name=player.short_name,
            date_of_birth=player.date_of_birth,
            age=calculate_age(player.date_of_birth),
            nationality=player.nationality,
            external_id=player.external_id,
            status=player.status,
            batting_hand=player.batting_hand,
            bowling_arm=player.bowling_arm,
            bowling_style=player.bowling_style,
            batting_style_display=batting_style_display(player.batting_hand),
            bowling_style_display=(
                bowling_style_display(
                    player.bowling_arm,
                    player.bowling_style,
                )
            ),
        ),
        active_teams=[
            PlayerTeamMembershipRead(
                team_id=item.team_id,
                team_name=item.team_name,
                team_short_name=item.team_short_name,
                role=item.role,
                squad_number=item.squad_number,
                joined_on=item.joined_on,
                left_on=item.left_on,
                is_active=item.is_active,
            )

            for item
            in memberships
        ],

        career=PlayerCareerRead(batting=batting, bowling=bowling),
        recent_matches=(history_items(recent_selections, batting_figures, bowling_figures))
    )