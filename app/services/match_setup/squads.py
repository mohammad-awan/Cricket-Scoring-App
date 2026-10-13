from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import AuditAction, MatchPlayer, MatchStatus
from app.repositories.match_setup import MatchSetupRepository
from app.schemas.match_setup import (
    MatchSetupRead,
    PlayerSummary,
    PlayingTeamSetup,
    SquadPlayerRead,
)
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.match_setup.presenters import match_setup_read, reload_match
from app.services.match_setup.tournament_snapshot import validate_tournament_lineup


async def get_active_squad(
    session: AsyncSession,
    match_id: UUID,
    team_id: UUID,
) -> list[SquadPlayerRead]:

    repository = (
        MatchSetupRepository(
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
            team_player_id=(
                item.id
            ),

            player=(
                PlayerSummary
                .model_validate(
                    item.player
                )
            ),

            role=(
                item.role
            ),

            squad_number=(
                item.squad_number
            ),
        )
        for item in squad
    ]


async def set_playing_team(
    session: AsyncSession,
    match_id: UUID,
    team_id: UUID,
    payload: PlayingTeamSetup,
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
                len(
                    payload.players
                )
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
                != len(
                    requested_ids
                )
            ):

                invalid_ids = (
                    requested_ids
                    - set(
                        memberships
                    )
                )

                invalid_text = (
                    ", ".join(
                        str(
                            item
                        )
                        for item
                        in sorted(
                            invalid_ids,
                            key=str,
                        )
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

            await validate_tournament_lineup(
                session,
                match,
                team_id,
                requested_ids,
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
                match_id=(
                    match.id
                ),

                team_id=(
                    team_id
                ),

                selections=(
                    selections
                ),
            )

            match.updated_at = (
                datetime.now(
                    UTC
                )
            )

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
                    "setup":
                        "playing_team",

                    "team_id":
                        str(
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
            "Playing team",
        ) from error
