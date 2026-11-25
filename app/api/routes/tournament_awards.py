from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter
from app.api.dependencies import OrganizerDependency, SessionDependency
from app.schemas.tournament_awards import (
    AwardConfirmation,
    AwardPublication,
    AwardRevocation,
    AwardSettingsUpdate,
    AwardVote,
    AwardWeights,
    PlayerOfMatchConfirmation,
)
from app.services.realtime import publish_tournament_event
from app.services.tournament_award_management import (
    cast_award_vote,
    confirm_award,
    confirm_player_of_match,
    list_confirmed_awards,
    publication_state,
    publish_awards,
    revoke_award,
    serialize_award,
    unpublish_awards,
    update_award_settings,
)
from app.services.tournament_awards import (
    get_award_settings,
    player_of_tournament_candidates,
    tournament_award_candidates,
    vote_tally,
)


router = APIRouter(prefix="/tournaments", tags=["Tournament Awards"])


@router.get("/{tournament_id}/awards/confirmed")
async def get_confirmed_awards(tournament_id: UUID, session: SessionDependency):
    return [serialize_award(award) for award in await list_confirmed_awards(session, tournament_id)]


@router.get("/{tournament_id}/awards/candidates")
async def award_candidates(tournament_id: UUID, session: SessionDependency):
    """Computed candidate rankings (evidence only, never final awards)."""

    return await tournament_award_candidates(session, tournament_id)


@router.post("/{tournament_id}/awards/player-of-tournament/candidates")
async def calculate_award_candidates(tournament_id: UUID, payload: AwardWeights, session: SessionDependency):
    """Preview Player of the Tournament rankings with alternative weights."""

    return await player_of_tournament_candidates(session, tournament_id, payload)


@router.get("/{tournament_id}/awards/settings")
async def read_award_settings(tournament_id: UUID, session: SessionDependency):
    return await get_award_settings(session, tournament_id)


@router.put("/{tournament_id}/awards/settings")
async def write_award_settings(
    tournament_id: UUID,
    payload: AwardSettingsUpdate,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    settings = await update_award_settings(session, tournament_id, payload.settings, payload.reason)
    await publish_tournament_event(tournament_id, "awards_changed", {"settings": True})
    return settings


@router.get("/{tournament_id}/awards/publication")
async def award_publication(tournament_id: UUID, session: SessionDependency):
    return await publication_state(session, tournament_id)


@router.post("/{tournament_id}/awards/publish")
async def publish_tournament_awards(
    tournament_id: UUID,
    payload: AwardPublication,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await publish_awards(session, tournament_id, payload.reason)
    await publish_tournament_event(tournament_id, "awards_published", {"count": len(result["awards"])})
    return result


@router.post("/{tournament_id}/awards/unpublish")
async def unpublish_tournament_awards(
    tournament_id: UUID,
    payload: AwardPublication,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await unpublish_awards(session, tournament_id, payload.reason)
    await publish_tournament_event(tournament_id, "awards_changed", {"published": False})
    return result


@router.post("/{tournament_id}/matches/{match_id}/player-of-match")
async def confirm_match_award(
    tournament_id: UUID,
    match_id: UUID,
    payload: PlayerOfMatchConfirmation,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    award = await confirm_player_of_match(session, tournament_id, match_id, payload.player_id, payload.reason)
    await publish_tournament_event(tournament_id, "awards_changed", {"award_code": award.award_code})
    return serialize_award(award)


@router.get("/{tournament_id}/awards/{award_code}/votes")
async def award_votes(tournament_id: UUID, award_code: str, session: SessionDependency, organizer: OrganizerDependency):
    return await vote_tally(session, tournament_id, award_code.strip().lower())


@router.post("/{tournament_id}/awards/{award_code}/votes")
async def vote_for_award(
    tournament_id: UUID,
    award_code: str,
    payload: AwardVote,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    return await cast_award_vote(
        session, tournament_id, award_code,
        voter=payload.voter, reason=payload.reason, player_id=payload.player_id,
        team_id=payload.team_id, score=payload.score,
    )


@router.post("/{tournament_id}/awards/{award_code}/confirm")
async def confirm_tournament_award(
    tournament_id: UUID,
    award_code: str,
    payload: AwardConfirmation,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    award = await confirm_award(
        session, tournament_id, award_code,
        player_id=payload.player_id, team_id=payload.team_id, reason=payload.reason, basis=payload.basis,
    )
    await publish_tournament_event(tournament_id, "awards_changed", {"award_code": award.award_code})
    return serialize_award(award)


@router.post("/{tournament_id}/awards/{award_code}/revoke")
async def revoke_tournament_award(
    tournament_id: UUID,
    award_code: str,
    payload: AwardRevocation,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    award = await revoke_award(session, tournament_id, award_code, payload.reason)
    await publish_tournament_event(tournament_id, "awards_changed", {"award_code": award.award_code})
    return serialize_award(award)
