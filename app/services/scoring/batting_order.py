from __future__ import annotations
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.batting_order import select_next_batter
from app.models import AuditAction, BatterRetirement, Delivery, Innings, Match, MatchPlayer
from app.repositories.scoring import ScoringRepository
from app.schemas.batting_order import (
    BatterLineupStatus,
    BattingOrderEntry,
    LiveBattingOrderRead,
    LiveBattingOrderUpdate,
)
from app.schemas.match_setup import PlayerSummary, TeamSummary
from app.services.common import add_audit_log, integrity_conflict, service_transaction
from app.services.scoring.state import (
    batter_status,
    ensure_scoreable,
    load_innings_state,
)
from app.services.scoring.types import DerivedState


def entered_player_ids(
    deliveries: list[Delivery],
    retirements: list[BatterRetirement],
    derived: DerivedState,
) -> set[UUID]:
    """
    Every batter who has walked out in this innings.
    Their batting-order slots are locked.
    """

    entered = {derived.striker_id, derived.non_striker_id}

    for item in deliveries:
        entered.update({item.striker_id, item.non_striker_id})

        if item.dismissed_player_id is not None:
            entered.add(item.dismissed_player_id)

        if item.next_batter_id is not None:
            entered.add(item.next_batter_id)

    for item in retirements:
        entered.add(item.player_id)

        if item.replacement_player_id is not None:
            entered.add(item.replacement_player_id)

    return entered


async def build_lineup(
    repository: ScoringRepository,
    *,
    match: Match,
    innings: Innings,
) -> tuple[list[MatchPlayer], set[UUID], LiveBattingOrderRead]:
    deliveries, retirements, derived = await load_innings_state(
        repository,
        match=match,
        innings=innings,
    )

    delivery_dismissed, retired = batter_status(deliveries, retirements, derived)
    entered = entered_player_ids(deliveries, retirements, derived)

    selections = await repository.get_playing_xi_with_players(match.id, innings.batting_team_id)

    if any(selection.batting_order is None for selection in selections):
        raise ValidationError("Every selected player must have a batting order.")

    crease = {derived.striker_id, derived.non_striker_id}

    def status_of(player_id: UUID) -> BatterLineupStatus:
        if player_id in delivery_dismissed:
            return "dismissed"
        if player_id in retired.retired_out_ids:
            return "retired_out"
        if player_id in crease:
            return "batting"
        if player_id in retired.retired_hurt_ids:
            return "retired_hurt"
        if player_id in entered:
            return "batted"
        return "yet_to_bat"

    unavailable = delivery_dismissed | retired.retired_out_ids
    ordered_ids = [selection.player_id for selection in selections]
    next_automatic = None

    # Who comes in at the next wicket under automatic
    # selection. Skipped once the side is all out.
    if not crease & unavailable:
        try:
            next_automatic = select_next_batter(
                ordered_ids,
                striker_id=derived.striker_id,
                non_striker_id=derived.non_striker_id,
                dismissed_player_ids=unavailable,
                dismissed_player_id=derived.striker_id,
                resumable_player_ids=set(retired.retired_hurt_ids),
            )
        except ValidationError:
            next_automatic = None

    lineup = LiveBattingOrderRead(
        match_id=match.id,
        innings_id=innings.id,
        innings_number=innings.innings_number,
        batting_team=TeamSummary.model_validate(innings.batting_team),
        entries=[
            BattingOrderEntry(
                batting_order=selection.batting_order,
                player=PlayerSummary.model_validate(selection.player),
                status=status_of(selection.player_id),
                locked=selection.player_id in entered,
            )
            for selection in selections
        ],
        next_automatic_batter_id=next_automatic,
    )

    return selections, entered, lineup


async def _current(
    repository: ScoringRepository,
    match_id: UUID,
    *,
    lock: bool,
) -> tuple[Match, Innings]:
    if lock:
        locked = await repository.lock_current_innings(match_id)

        if locked is None:
            raise NotFoundError("First innings has not been configured")

    match = await repository.get_match(match_id)

    if match is None:
        raise NotFoundError("Match not found")

    # Loads the team relationships; with the lock held
    # this is the same row.
    innings = await repository.get_current_innings(match_id)

    if innings is None:
        raise NotFoundError("First innings has not been configured")

    return match, innings


async def get_live_batting_order(
    session: AsyncSession,
    match_id: UUID,
) -> LiveBattingOrderRead:
    repository = ScoringRepository(session)
    match, innings = await _current(repository, match_id, lock=False)

    _, _, lineup = await build_lineup(repository, match=match, innings=innings)
    return lineup


async def rearrange_batting_order(
    session: AsyncSession,
    match_id: UUID,
    payload: LiveBattingOrderUpdate,
) -> LiveBattingOrderRead:
    """
    Reprioritise batters who have not yet batted.

    Runs under the innings row lock, so it is
    serialised with deliveries and wickets: the next
    automatic selection always sees either the old or
    the new order, never a mix. Batters who have
    entered keep their slots, so recorded history is
    never rewritten.
    """

    repository = ScoringRepository(session)

    try:

        async with service_transaction(session):
            match, innings = await _current(repository, match_id, lock=True)
            ensure_scoreable(match, innings)

            selections, entered, _ = await build_lineup(
                repository,
                match=match,
                innings=innings,
            )

            movable = [
                selection
                for selection in selections
                if selection.player_id not in entered
            ]

            movable_ids = {selection.player_id for selection in movable}
            requested = payload.ordered_player_ids

            if set(requested) != movable_ids:
                unknown = set(requested) - movable_ids

                if unknown & entered:
                    raise ValidationError(
                        "Batters who have already entered the innings "
                        "cannot be moved."
                    )

                if unknown:
                    raise ValidationError(
                        "Every player must be a yet-to-bat member "
                        "of the batting playing XI."
                    )

                raise ValidationError(
                    "The new order must list every batter "
                    "who has not yet batted."
                )

            previous = [
                str(selection.player_id)
                for selection in movable
            ]

            # Re-use the same slots so positions stay 1..N.
            slots = sorted(selection.batting_order for selection in movable)
            by_player = {selection.player_id: selection for selection in movable}

            # Two phases avoid colliding with the unique
            # (match, team, batting_order) constraint.
            for selection in movable:
                selection.batting_order = None

            await session.flush()

            for slot, player_id in zip(slots, requested, strict=True):
                by_player[player_id].batting_order = slot

            await session.flush()

            add_audit_log(
                session,
                entity_type="innings",
                entity_id=innings.id,
                action=AuditAction.UPDATED,
                details={
                    "change": "batting_order",
                    "match_id": str(match.id),
                    "team_id": str(innings.batting_team_id),
                    "slots": slots,
                    "previous_order": previous,
                    "new_order": [str(player_id) for player_id in requested],
                    "reason": payload.reason,
                },
            )

            await session.flush()

            _, _, lineup = await build_lineup(
                repository,
                match=match,
                innings=innings,
            )

    except IntegrityError as error:
        raise integrity_conflict(error, "Batting order") from error

    return lineup
