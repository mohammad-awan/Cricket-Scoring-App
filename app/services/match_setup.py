from __future__ import annotations
from datetime import UTC, datetime
from math import ceil
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    AuditAction,
    Innings,
    InningsStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    Team,
    TeamStatus,
    TournamentStatus,
    VenueStatus,
)
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.common import PageResponse
from app.schemas.match_setup import (
    InningsSetupRead,
    MatchCreate,
    MatchListRead,
    MatchReadinessRead,
    MatchSetupRead,
    MatchUpdate,
    OpeningInningsSetup,
    PlayerSummary,
    PlayingTeamSetup,
    SquadPlayerRead,
    TeamSummary,
    TossSetup,
    TournamentSummary,
    VenueSummary,
)

from app.services.common import add_audit_log, integrity_conflict, service_transaction


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def derive_first_innings_teams(match: Match) -> tuple[UUID, UUID]:

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
        if match.toss_winner_id
        == match.team_a_id
        else match.team_a_id
    )

    if match.toss_decision.value== "bat":
        return (match.toss_winner_id, other_team_id)

    return (other_team_id, match.toss_winner_id)


def _playing_team_ids(match: Match, team_id: UUID) -> set[UUID]:
    return {
        selection.player_id
        for selection in match.players
        if selection.team_id
        == team_id
    }


def _readiness(match: Match) -> MatchReadinessRead:

    team_a_ids = _playing_team_ids(match, match.team_a_id)
    team_b_ids = _playing_team_ids(match, match.team_b_id)
    toss_complete = (
        match.toss_winner_id
        in {
            match.team_a_id,
            match.team_b_id,
        }
        and match.toss_decision
        is not None
    )
    team_a_players_complete = len(team_a_ids) == match.players_per_side
    team_b_players_complete = len(team_b_ids) == match.players_per_side
    first_innings = next(
        (
            innings
            for innings
            in match.innings
            if innings.innings_number
            == 1
        ),
        None,
    )

    opening_innings_complete = bool(
        first_innings
        and first_innings.striker_id
        and first_innings.non_striker_id
        and first_innings.current_bowler_id
        and first_innings.striker_id
        != first_innings.non_striker_id
    )

    details_complete = (
        match.venue_id is not None
        and match.scheduled_at is not None
    )

    missing: list[str] = []

    if match.venue_id is None:
        missing.append("venue")

    if match.scheduled_at is None:
        missing.append("scheduled_at")

    if not toss_complete:
        missing.append("toss")

    if not team_a_players_complete:
        missing.append("team_a_playing_team")

    if not team_b_players_complete:
        missing.append("team_b_playing_team")

    if not opening_innings_complete:
        missing.append("opening_innings")

    return MatchReadinessRead(
        details_complete=details_complete,
        toss_complete=toss_complete,
        team_a_players_complete=(team_a_players_complete),
        team_b_players_complete=(team_b_players_complete),
        opening_innings_complete=(opening_innings_complete),
        ready=not missing,
        missing=missing,
    )


def _match_setup_read(match: Match) -> MatchSetupRead:

    return MatchSetupRead(
        id=match.id,
        title=match.title,
        match_number=(match.match_number),
        team_a=(TeamSummary.model_validate(match.team_a)),
        team_b=(TeamSummary.model_validate(match.team_b)),
        tournament=(
            TournamentSummary
            .model_validate(
                match.tournament
            )
            if match.tournament
            else None
        ),

        venue=(
            VenueSummary.model_validate(
                match.venue
            )
            if match.venue
            else None
        ),

        match_type=(match.match_type),
        players_per_side=(match.players_per_side),
        total_overs=(match.total_overs),
        balls_per_over=(match.balls_per_over),
        innings_per_team=(match.innings_per_team),
        scheduled_at=(match.scheduled_at),
        status=match.status,
        created_at=(match.created_at),
        updated_at=(match.updated_at),
        toss_winner=(
            TeamSummary.model_validate(
                match.toss_winner
            )
            if match.toss_winner
            else None
        ),
        toss_decision=(match.toss_decision),
        players=match.players,
        innings=[
            InningsSetupRead
            .model_validate(item)
            for item
            in match.innings
        ],

        readiness=_readiness(
            match
        ),
    )


async def _require_active_team(repository: MatchSetupRepository, team_id: UUID, label: str) -> Team:
    team = await repository.get_team(team_id)
    if team is None:
        raise NotFoundError(f"{label} not found")

    if (
        team.status
        != TeamStatus.ACTIVE
        or team.archived_at
        is not None
    ):
        raise ConflictError(
            f"{label} must be active"
        )

    return team


async def _validate_match_references(
    repository: MatchSetupRepository,
    *,
    team_a_id: UUID,
    team_b_id: UUID,
    venue_id: UUID | None,
    tournament_id: UUID | None,
) -> tuple[Team, Team]:

    if team_a_id == team_b_id:
        raise ValidationError(
            "Team A and Team B "
            "must be different"
        )

    team_a = (
        await _require_active_team(
            repository,
            team_a_id,
            "Team A",
        )
    )

    team_b = (
        await _require_active_team(
            repository,
            team_b_id,
            "Team B",
        )
    )

    # Venue is optional while the match is draft;
    # mark_match_ready() requires it.
    if venue_id is not None:

        venue = (
            await repository.get_venue(
                venue_id
            )
        )

        if venue is None:
            raise NotFoundError(
                "Venue not found"
            )

        if (
            venue.status
            != VenueStatus.ACTIVE
            or venue.archived_at
            is not None
        ):
            raise ConflictError(
                "Venue must be active"
            )

    if tournament_id is not None:

        tournament = (
            await repository
            .get_tournament(
                tournament_id
            )
        )

        if tournament is None:
            raise NotFoundError(
                "Tournament not found"
            )

        if (
            tournament.status
            == TournamentStatus.ARCHIVED
            or tournament.archived_at
            is not None
        ):
            raise ConflictError(
                "Archived tournament "
                "cannot be used for a match"
            )

    return (
        team_a,
        team_b,
    )


async def create_match(session: AsyncSession, payload: MatchCreate) -> MatchSetupRead:
    repository = MatchSetupRepository(session)

    try:
        async with service_transaction(session):

            team_a, team_b = (
                await _validate_match_references(
                    repository,
                    team_a_id=payload.team_a_id,
                    team_b_id=payload.team_b_id,
                    venue_id=payload.venue_id,
                    tournament_id=payload.tournament_id,
                )
            )

            title = _clean_optional(payload.title)

            if title is None:
                title = (
                    f"{team_a.short_name} "
                    f"vs "
                    f"{team_b.short_name}"
                )

            match = Match(
                title=title,
                match_number=payload.match_number,
                team_a_id=payload.team_a_id,
                team_b_id=payload.team_b_id,
                tournament_id=payload.tournament_id,
                venue_id=payload.venue_id,
                match_type=payload.match_type,
                players_per_side=payload.players_per_side,
                total_overs=payload.total_overs,
                balls_per_over=payload.balls_per_over,
                innings_per_team=payload.innings_per_team,
                scheduled_at=payload.scheduled_at,
                status=MatchStatus.DRAFT,
            )

            session.add(match)
            await session.flush()

            add_audit_log(
                session,
                entity_type="match",
                entity_id=match.id,
                action=AuditAction.CREATED,
                details={
                    "team_a_id": str(match.team_a_id),
                    "team_b_id": str(match.team_b_id),
                    "status": MatchStatus.DRAFT.value,
                },
            )

            await session.flush()

        loaded = await repository.get_match(match.id )
        if loaded is None:
            raise NotFoundError(
                "Match not found "
                "after creation"
            )

        return _match_setup_read(
            loaded
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Match",
        ) from error


async def list_matches(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    search: str | None,
    match_status: MatchStatus | None,
) -> PageResponse[MatchListRead]:
    repository = MatchSetupRepository(session)
    items = (
        await repository.list_matches(
            page=page,
            page_size=page_size,
            search=search,
            match_status=match_status,
        )
    )
    total = (
        await repository.count_matches(search=search, match_status=(match_status),)
    )
    return PageResponse[MatchListRead](
        items=[
            MatchListRead
            .model_validate(item)
            for item
            in items
        ],
        page=page,
        page_size=page_size,
        total=total,
        pages=(ceil(total / page_size) if total else 0)
    )


async def get_match_setup(session: AsyncSession, match_id: UUID) -> MatchSetupRead:
    match = await MatchSetupRepository(session).get_match(match_id)
    if match is None:
        raise NotFoundError("Match not found")

    return _match_setup_read(match)


async def update_match(
    session: AsyncSession,
    match_id: UUID,
    payload: MatchUpdate,
) -> MatchSetupRead:

    repository = MatchSetupRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:

        async with service_transaction(session):
            match = await repository.get_match(match_id, for_update=True)

            if match is None:
                raise NotFoundError("Match not found")

            if match.status != MatchStatus.DRAFT:
                raise ConflictError(
                    "Only draft matches "
                    "can be edited"
                )

            for required_field in (
                "team_a_id",
                "team_b_id",
                "match_type",
                "players_per_side",
                "balls_per_over",
                "innings_per_team",
            ):

                if (
                    required_field in data
                    and data[
                        required_field
                    ]
                    is None
                ):
                    raise ValidationError(
                        f"{required_field} "
                        "cannot be null"
                    )

            team_a_id = data.get("team_a_id", match.team_a_id)
            team_b_id = data.get("team_b_id", match.team_b_id)
            venue_id = data.get("venue_id", match.venue_id)
            tournament_id = data.get("tournament_id", match.tournament_id)

            teams_changed = (
                team_a_id
                != match.team_a_id
                or team_b_id
                != match.team_b_id
            )

            if (
                teams_changed
                and (
                    match.toss_winner_id
                    is not None
                    or match.players
                    or match.innings
                )
            ):
                raise ConflictError(
                    "Teams cannot be changed "
                    "after toss, playing team, "
                    "or innings setup has started"
                )

            if (
                "players_per_side" in data
                and data["players_per_side"]
                != match.players_per_side
                and match.players
            ):
                raise ConflictError(
                    "Players per side cannot be "
                    "changed after a playing team "
                    "has been selected"
                )

            await _validate_match_references(
                repository,
                team_a_id=team_a_id,
                team_b_id=team_b_id,
                venue_id=venue_id,
                tournament_id=(tournament_id),
            )

            for field in (
                "match_number",
                "team_a_id",
                "team_b_id",
                "tournament_id",
                "venue_id",
                "match_type",
                "players_per_side",
                "total_overs",
                "balls_per_over",
                "innings_per_team",
                "scheduled_at",
            ):

                if field in data:
                    setattr(
                        match,
                        field,
                        data[field],
                    )

            if "title" in data:

                match.title = _clean_optional(data["title"])

            match.updated_at = datetime.now(UTC)
            await session.flush()
            add_audit_log(
                session,
                entity_type="match",
                entity_id=match.id,
                action=(AuditAction.UPDATED),
                details={"fields": sorted(data)},
            )
            await session.flush()

        loaded = await repository.get_match(match_id)
        if loaded is None:
            raise NotFoundError(
                "Match not found"
            )

        return _match_setup_read(loaded)

    except IntegrityError as error:
        raise integrity_conflict(error, "Match") from error


async def set_toss(
    session: AsyncSession,
    match_id: UUID,
    payload: TossSetup,
) -> MatchSetupRead:

    repository = MatchSetupRepository(session)
    async with service_transaction(session):
        match = (
            await repository.get_match(
                match_id,
                for_update=True,
            )
        )

        if match is None:
            raise NotFoundError("Match not found")
        
        if match.status != MatchStatus.DRAFT:
            raise ConflictError(
                "Toss can only be changed "
                "while the match is draft"
            )

        if (
            payload.winner_team_id
            not in {
                match.team_a_id,
                match.team_b_id,
            }
        ):
            raise ValidationError(
                "Toss winner must be "
                "Team A or Team B"
            )

        if match.innings:
            raise ConflictError(
                "Toss cannot be changed "
                "after opening innings setup "
                "has been created"
            )

        match.toss_winner_id = payload.winner_team_id
        match.toss_decision = payload.decision
        match.updated_at = datetime.now(UTC)
        await session.flush()
        add_audit_log(
            session,
            entity_type="match",
            entity_id=match.id,
            action=AuditAction.UPDATED,
            details={
                "setup": "toss",

                "winner_team_id": str(payload.winner_team_id),
                "decision": payload.decision.value,
            },
        )

        await session.flush()

    loaded = await repository.get_match(match_id)

    if loaded is None:
        raise NotFoundError(
            "Match not found"
        )

    return _match_setup_read(
        loaded
    )


async def get_active_squad(
    session: AsyncSession,
    match_id: UUID,
    team_id: UUID,
) -> list[SquadPlayerRead]:

    repository = MatchSetupRepository(session)
    match = await repository.get_match(match_id)
    if match is None:
        raise NotFoundError(
            "Match not found"
        )

    if team_id not in {
        match.team_a_id,
        match.team_b_id,
    }:
        raise ValidationError(
            "Requested team does not "
            "belong to this match"
        )

    squad = (
        await repository
        .get_active_squad(
            team_id
        )
    )

    return [
        SquadPlayerRead(
            team_player_id=item.id,
            player=(
                PlayerSummary
                .model_validate(
                    item.player
                )
            ),
            role=item.role,
            squad_number=(
                item.squad_number
            ),
        )

        for item
        in squad
    ]


async def set_playing_team(
    session: AsyncSession,
    match_id: UUID,
    team_id: UUID,
    payload: PlayingTeamSetup,
) -> MatchSetupRead:

    repository = MatchSetupRepository(session)
    try:

        async with service_transaction(
            session
        ):

            match = (
                await repository
                .get_match(
                    match_id,
                    for_update=True,
                )
            )

            if match is None:
                raise NotFoundError(
                    "Match not found"
                )

            if (
                match.status
                != MatchStatus.DRAFT
            ):
                raise ConflictError(
                    "Playing team can only "
                    "be changed while "
                    "the match is draft"
                )

            if team_id not in {
                match.team_a_id,
                match.team_b_id,
            }:
                raise ValidationError(
                    "Playing team "
                    "does not belong "
                    "to this match"
                )

            if match.innings:
                raise ConflictError(
                    "Playing team cannot "
                    "be changed after "
                    "opening innings setup "
                    "has been created"
                )

            if (
                len(payload.players)
                != match.players_per_side
            ):
                raise ValidationError(
                    "This match requires exactly "
                    f"{match.players_per_side} "
                    "players per side, but "
                    f"{len(payload.players)} "
                    "were provided"
                )

            requested_ids = {
                item.player_id
                for item
                in payload.players
            }

            memberships = (
                await repository
                .get_active_squad_memberships(
                    team_id,
                    requested_ids,
                )
            )

            if (
                len(memberships)
                != len(requested_ids)
            ):

                invalid_ids = (
                    requested_ids
                    - set(
                        memberships
                    )
                )

                invalid_text = ", ".join(
                    str(item)
                    for item
                    in sorted(
                        invalid_ids,
                        key=str,
                    )
                )

                raise ValidationError(
                    "Every selected player "
                    "must belong to the "
                    "team's active squad"
                    + (
                        ". Invalid player IDs: "
                        f"{invalid_text}"
                        if invalid_text
                        else ""
                    )
                )

            selections = [
                MatchPlayer(
                    match_id=(
                        match.id
                    ),

                    team_id=(
                        team_id
                    ),

                    player_id=(
                        item.player_id
                    ),

                    batting_order=(
                        item.batting_order
                    ),

                    role=(
                        memberships[
                            item.player_id
                        ].role
                    ),

                    is_captain=(
                        item.is_captain
                    ),

                    is_wicket_keeper=(
                        item
                        .is_wicket_keeper
                    ),
                )

                for item
                in payload.players
            ]

            await repository.replace_playing_xi(
                match_id=match.id,

                team_id=team_id,

                selections=selections,
            )

            match.updated_at = (
                datetime.now(UTC)
            )

            add_audit_log(
                session,

                entity_type="match",

                entity_id=match.id,

                action=(
                    AuditAction.UPDATED
                ),

                details={
                    "setup": "playing_team",

                    "team_id": str(
                        team_id
                    ),

                    "player_ids": [
                        str(
                            item.player_id
                        )
                        for item
                        in payload.players
                    ],
                },
            )

            await session.flush()

        loaded = (
            await repository.get_match(
                match_id
            )
        )

        if loaded is None:
            raise NotFoundError(
                "Match not found"
            )

        return _match_setup_read(
            loaded
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Playing team",
        ) from error


async def setup_opening_innings(
    session: AsyncSession,
    match_id: UUID,
    payload: OpeningInningsSetup,
) -> MatchSetupRead:

    repository = MatchSetupRepository(
        session
    )

    try:

        async with service_transaction(
            session
        ):

            match = (
                await repository
                .get_match(
                    match_id,
                    for_update=True,
                )
            )

            if match is None:
                raise NotFoundError(
                    "Match not found"
                )

            if (
                match.status
                != MatchStatus.DRAFT
            ):
                raise ConflictError(
                    "Opening innings can "
                    "only be configured "
                    "while the match is draft"
                )

            readiness = _readiness(
                match
            )

            if not readiness.toss_complete:
                raise ValidationError(
                    "Complete the toss "
                    "before innings setup"
                )

            if (
                not readiness
                .team_a_players_complete
                or not readiness
                .team_b_players_complete
            ):
                raise ValidationError(
                    "Both playing teams "
                    "must contain exactly "
                    f"{match.players_per_side} players"
                )

            (
                batting_team_id,
                bowling_team_id,
            ) = derive_first_innings_teams(
                match
            )

            batting_xi = _playing_team_ids(
                match,
                batting_team_id,
            )

            bowling_xi = _playing_team_ids(
                match,
                bowling_team_id,
            )

            if (
                payload.striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Striker must belong "
                    "to the batting team's "
                    "playing team"
                )

            if (
                payload.non_striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Non-striker must belong "
                    "to the batting team's "
                    "playing team"
                )

            if (
                payload.opening_bowler_id
                not in bowling_xi
            ):
                raise ValidationError(
                    "Opening bowler must "
                    "belong to the bowling "
                    "team's playing team"
                )

            first_innings = (
                await repository
                .get_first_innings(
                    match.id
                )
            )

            if first_innings is None:

                first_innings = Innings(
                    match_id=match.id,

                    innings_number=1,

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
                    first_innings
                )

                audit_action = (
                    AuditAction.CREATED
                )

            else:

                if first_innings.deliveries:
                    raise ConflictError(
                        "Opening participants "
                        "cannot be changed "
                        "after scoring starts"
                    )

                first_innings.batting_team_id = (
                    batting_team_id
                )

                first_innings.bowling_team_id = (
                    bowling_team_id
                )

                first_innings.status = (
                    InningsStatus.PENDING
                )

                first_innings.striker_id = (
                    payload.striker_id
                )

                first_innings.non_striker_id = (
                    payload.non_striker_id
                )

                first_innings.current_bowler_id = (
                    payload.opening_bowler_id
                )

                first_innings.updated_at = (
                    datetime.now(UTC)
                )

                audit_action = (
                    AuditAction.UPDATED
                )

            await session.flush()

            match.updated_at = (
                datetime.now(UTC)
            )

            add_audit_log(
                session,

                entity_type="innings",

                entity_id=(
                    first_innings.id
                ),

                action=(
                    audit_action
                ),

                details={
                    "match_id": str(
                        match.id
                    ),

                    "innings_number": 1,

                    "batting_team_id": str(
                        batting_team_id
                    ),

                    "bowling_team_id": str(
                        bowling_team_id
                    ),

                    "striker_id": str(
                        payload.striker_id
                    ),

                    "non_striker_id": str(
                        payload.non_striker_id
                    ),

                    "opening_bowler_id": str(
                        payload
                        .opening_bowler_id
                    ),
                },
            )

            await session.flush()

        loaded = (
            await repository
            .get_match(
                match_id
            )
        )

        if loaded is None:
            raise NotFoundError(
                "Match not found"
            )

        return _match_setup_read(
            loaded
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Opening innings",
        ) from error


async def mark_match_ready(session: AsyncSession, match_id: UUID) -> MatchSetupRead:
    repository = MatchSetupRepository(session)
    try:
        async with service_transaction(session):
            match = (
                await repository
                .get_match(
                    match_id,
                    for_update=True,
                )
            )

            if match is None:
                raise NotFoundError("Match not found")

            if match.status == MatchStatus.READY:
                return _match_setup_read(match)

            if match.status != MatchStatus.DRAFT:
                raise ConflictError("Only a draft match " "can move to ready")

            if match.venue_id is None:
                raise ValidationError(
                    "Venue is required "
                    "before the match "
                    "can be ready"
                )

            if match.scheduled_at is None:
                raise ValidationError(
                    "Scheduled date/time "
                    "is required before "
                    "the match can be ready"
                )

            await _validate_match_references(
                repository,
                team_a_id=(match.team_a_id),
                team_b_id=(match.team_b_id),
                venue_id=(match.venue_id),
                tournament_id=(match.tournament_id),
            )
            readiness = _readiness(match)

            if not readiness.ready:
                raise ValidationError(
                    "Match setup is incomplete. "
                    "Missing: "
                    + ", ".join(
                        readiness.missing
                    )
                )

            team_a_memberships = (
                await repository
                .get_active_squad_memberships(
                    match.team_a_id,

                    _playing_team_ids(
                        match,
                        match.team_a_id,
                    ),
                )
            )

            team_b_memberships = (
                await repository
                .get_active_squad_memberships(
                    match.team_b_id,

                    _playing_team_ids(
                        match,
                        match.team_b_id,
                    ),
                )
            )

            if len(team_a_memberships) != match.players_per_side:
                raise ValidationError(
                    "Team A playing team "
                    "contains a player who "
                    "is no longer in the "
                    "active squad"
                )

            if len(team_b_memberships) != match.players_per_side:
                raise ValidationError(
                    "Team B playing team "
                    "contains a player who "
                    "is no longer in the "
                    "active squad"
                )

            first_innings = next(
                item
                for item
                in match.innings
                if item.innings_number
                == 1
            )

            (
                batting_team_id,
                bowling_team_id,
            ) = derive_first_innings_teams(
                match
            )

            if (
                first_innings
                .batting_team_id
                != batting_team_id
                or first_innings
                .bowling_team_id
                != bowling_team_id
            ):
                raise ValidationError(
                    "First innings teams "
                    "do not match the "
                    "toss decision"
                )

            batting_xi = _playing_team_ids(
                match, batting_team_id)

            bowling_xi = _playing_team_ids(
                match,
                bowling_team_id,
            )

            if (
                first_innings.striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Configured striker "
                    "is no longer in the "
                    "batting team"
                )

            if (
                first_innings
                .non_striker_id
                not in batting_xi
            ):
                raise ValidationError(
                    "Configured non-striker "
                    "is no longer in the "
                    "batting team"
                )

            if (
                first_innings
                .current_bowler_id
                not in bowling_xi
            ):
                raise ValidationError(
                    "Configured opening "
                    "bowler is no longer "
                    "in the bowling team"
                )

            match.status = MatchStatus.READY
            match.updated_at = datetime.now(UTC)
            await session.flush()

            add_audit_log(
                session,

                entity_type="match",

                entity_id=match.id,

                action=(
                    AuditAction.UPDATED
                ),

                details={
                    "transition": (
                        "draft_to_ready"
                    ),

                    "status": (
                        MatchStatus
                        .READY
                        .value
                    ),
                },
            )

            await session.flush()

        loaded = (await repository.get_match(match_id))
        if loaded is None:
            raise NotFoundError("Match not found")

        return _match_setup_read(loaded)

    except IntegrityError as error:
        raise integrity_conflict(error, "Match readiness") from error