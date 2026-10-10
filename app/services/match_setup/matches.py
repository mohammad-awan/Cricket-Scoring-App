from __future__ import annotations
from datetime import UTC, datetime
from math import ceil
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, Match, MatchStatus
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.common import PageResponse
from app.schemas.match_setup import MatchCreate, MatchListRead, MatchSetupRead, MatchUpdate
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.utils.text import clean_optional
from app.services.match_setup.presenters import match_setup_read, reload_match
from app.services.match_setup.validators import validate_match_references


async def create_match(
    session: AsyncSession,
    payload: MatchCreate,
) -> MatchSetupRead:

    repository = (
        MatchSetupRepository(
            session
        )
    )

    try:

        async with service_transaction(
            session
        ):

            (
                team_a,
                team_b,
            ) = (
                await validate_match_references(
                    repository,

                    team_a_id=(
                        payload.team_a_id
                    ),

                    team_b_id=(
                        payload.team_b_id
                    ),

                    venue_id=(
                        payload.venue_id
                    ),

                    tournament_id=(
                        payload.tournament_id
                    ),
                )
            )

            title = clean_optional(
                payload.title
            )

            if title is None:

                title = (
                    f"{team_a.short_name} "
                    f"vs "
                    f"{team_b.short_name}"
                )

            match = Match(
                title=title,

                match_number=(
                    payload.match_number
                ),

                team_a_id=(
                    payload.team_a_id
                ),

                team_b_id=(
                    payload.team_b_id
                ),

                tournament_id=(
                    payload.tournament_id
                ),

                venue_id=(
                    payload.venue_id
                ),

                match_type=(
                    payload.match_type
                ),

                players_per_side=(
                    payload.players_per_side
                ),

                total_overs=(
                    payload.total_overs
                ),

                balls_per_over=(
                    payload.balls_per_over
                ),

                innings_per_team=(
                    payload.innings_per_team
                ),

                scheduled_at=(
                    payload.scheduled_at
                ),

                status=(
                    MatchStatus.DRAFT
                ),
            )

            session.add(
                match
            )

            await session.flush()

            add_audit_log(
                session,

                entity_type=(
                    "match"
                ),

                entity_id=(
                    match.id
                ),

                action=(
                    AuditAction.CREATED
                ),

                details={
                    "team_a_id":
                        str(
                            match.team_a_id
                        ),

                    "team_b_id":
                        str(
                            match.team_b_id
                        ),

                    "status":
                        MatchStatus
                        .DRAFT
                        .value,
                },
            )

            await session.flush()

        loaded = await reload_match(
            session,
            repository,
            match.id,
        )

        return match_setup_read(
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
    match_status: (
        MatchStatus | None
    ),
) -> PageResponse[MatchListRead]:

    repository = (
        MatchSetupRepository(
            session
        )
    )

    items = await repository.list_matches(
        page=page,
        page_size=page_size,
        search=search,
        match_status=match_status,
    )

    total = (
        await repository
        .count_matches(
            search=search,
            match_status=match_status,
        )
    )

    return PageResponse[
        MatchListRead
    ](
        items=[
            MatchListRead.model_validate(
                item
            )
            for item in items
        ],

        page=page,

        page_size=page_size,

        total=total,

        pages=(
            ceil(
                total / page_size
            )
            if total
            else 0
        ),
    )


async def get_match_setup(
    session: AsyncSession,
    match_id: UUID,
) -> MatchSetupRead:

    match = (
        await MatchSetupRepository(
            session
        )
        .get_match(
            match_id
        )
    )

    if match is None:
        raise NotFoundError(
            "Match not found"
        )

    return match_setup_read(
        match
    )


async def update_match(
    session: AsyncSession,
    match_id: UUID,
    payload: MatchUpdate,
) -> MatchSetupRead:

    repository = (
        MatchSetupRepository(
            session
        )
    )

    data = payload.model_dump(
        exclude_unset=True
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
                    required_field
                    in data
                    and data[
                        required_field
                    ]
                    is None
                ):
                    raise ValidationError(
                        f"{required_field} "
                        "cannot be null"
                    )

            team_a_id = data.get(
                "team_a_id",
                match.team_a_id,
            )

            team_b_id = data.get(
                "team_b_id",
                match.team_b_id,
            )

            venue_id = data.get(
                "venue_id",
                match.venue_id,
            )

            tournament_id = data.get(
                "tournament_id",
                match.tournament_id,
            )

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
                "players_per_side"
                in data
                and data[
                    "players_per_side"
                ]
                != match.players_per_side
                and match.players
            ):
                raise ConflictError(
                    "Players per side cannot be "
                    "changed after a playing team "
                    "has been selected"
                )

            await validate_match_references(
                repository,

                team_a_id=(
                    team_a_id
                ),

                team_b_id=(
                    team_b_id
                ),

                venue_id=(
                    venue_id
                ),

                tournament_id=(
                    tournament_id
                ),
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

                match.title = (
                    clean_optional(
                        data["title"]
                    )
                )

            match.updated_at = (
                datetime.now(
                    UTC
                )
            )

            await session.flush()

            add_audit_log(
                session,

                entity_type=(
                    "match"
                ),

                entity_id=(
                    match.id
                ),

                action=(
                    AuditAction.UPDATED
                ),

                details={
                    "fields":
                        sorted(
                            data
                        )
                },
            )

            await session.flush()

        loaded = await reload_match(
            session,
            repository,
            match_id,
        )

        return match_setup_read(
            loaded
        )

    except IntegrityError as error:

        raise integrity_conflict(
            error,
            "Match",
        ) from error
