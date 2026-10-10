from __future__ import annotations
from uuid import UUID
from app.core.exceptions import ValidationError
from app.models import Match
from app.schemas.match_setup import MatchReadinessRead


def derive_first_innings_teams(
    match: Match,
) -> tuple[UUID, UUID]:

    if (
        match.toss_winner_id is None
        or match.toss_decision is None
    ):
        raise ValidationError(
            "Toss must be completed "
            "before innings setup"
        )

    if match.toss_winner_id not in {
        match.team_a_id,
        match.team_b_id,
    }:
        raise ValidationError(
            "Toss winner must belong "
            "to this match"
        )

    other_team_id = (
        match.team_b_id
        if (
            match.toss_winner_id
            == match.team_a_id
        )
        else match.team_a_id
    )

    if (
        match.toss_decision.value
        == "bat"
    ):
        return (
            match.toss_winner_id,
            other_team_id,
        )

    return (
        other_team_id,
        match.toss_winner_id,
    )


def playing_team_ids(
    match: Match,
    team_id: UUID,
) -> set[UUID]:

    return {
        selection.player_id
        for selection in match.players
        if selection.team_id == team_id
    }


def evaluate_readiness(
    match: Match,
) -> MatchReadinessRead:

    team_a_ids = playing_team_ids(
        match,
        match.team_a_id,
    )

    team_b_ids = playing_team_ids(
        match,
        match.team_b_id,
    )

    toss_complete = (
        match.toss_winner_id
        in {
            match.team_a_id,
            match.team_b_id,
        }
        and match.toss_decision is not None
    )

    team_a_players_complete = (
        len(team_a_ids)
        == match.players_per_side
    )

    team_b_players_complete = (
        len(team_b_ids)
        == match.players_per_side
    )

    first_innings = next(
        (
            innings
            for innings in match.innings
            if innings.innings_number == 1
        ),
        None,
    )

    opening_innings_complete = bool(
        first_innings
        and first_innings.striker_id
        and first_innings.non_striker_id
        and first_innings.current_bowler_id
        and (
            first_innings.striker_id
            != first_innings.non_striker_id
        )
    )

    details_complete = (
        match.venue_id is not None
        and match.scheduled_at is not None
    )

    missing: list[str] = []

    if match.venue_id is None:
        missing.append(
            "venue"
        )

    if match.scheduled_at is None:
        missing.append(
            "scheduled_at"
        )

    if not toss_complete:
        missing.append(
            "toss"
        )

    if not team_a_players_complete:
        missing.append(
            "team_a_playing_team"
        )

    if not team_b_players_complete:
        missing.append(
            "team_b_playing_team"
        )

    if not opening_innings_complete:
        missing.append(
            "opening_innings"
        )

    return MatchReadinessRead(
        details_complete=(
            details_complete
        ),

        toss_complete=(
            toss_complete
        ),

        team_a_players_complete=(
            team_a_players_complete
        ),

        team_b_players_complete=(
            team_b_players_complete
        ),

        opening_innings_complete=(
            opening_innings_complete
        ),

        ready=not missing,

        missing=missing,
    )
