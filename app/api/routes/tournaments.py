from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query, status
from app.api.dependencies import OrganizerDependency, QueryDependency, SessionDependency
from app.domain.tournament_rules import FormatCode, TournamentRules, rules_preset
from app.schemas.common import PageResponse
from app.schemas.tournaments import (
    CompetitionConfigUpdate,
    GroupCreate,
    RegistrationDecision,
    RosterAdd,
    RosterRead,
    RulePropagationRead,
    RulePropagationRequest,
    RuleVersionCreate,
    RuleVersionRead,
    TournamentAuditRead,
    TournamentCaptainUpdate,
    TournamentCreate,
    TournamentDetailRead,
    TournamentGroupAssignment,
    TournamentGroupRead,
    TournamentPreview,
    TournamentPublishRequest,
    TournamentRead,
    TournamentRosterAvailability,
    TournamentRosterLockRequest,
    TournamentRulesPreview,
    TournamentRuleValidationRead,
    TournamentTeamRead,
    TournamentTransitionsRead,
    TournamentTeamRegister,
    TournamentUpdate,
    TournamentVenueRead,
    TournamentWithdrawalRequest,
    TransitionRequest,
    VenueAssign,
)
from app.services import tournaments as tournament_services
from app.services.tournaments import archive_tournament, create_tournament, get_tournament, list_tournaments, update_tournament


router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.post("", response_model=TournamentRead, status_code=status.HTTP_201_CREATED)
async def create_tournament_endpoint(
    payload: TournamentCreate,
    session: SessionDependency,
) -> TournamentRead:
    return await create_tournament(session, payload)


@router.get("", response_model=PageResponse[TournamentRead])
async def list_tournaments_endpoint(
    query: QueryDependency,
    session: SessionDependency,
) -> PageResponse[TournamentRead]:
    return await list_tournaments(session, query)


@router.get("/{tournament_id}", response_model=TournamentRead)
async def get_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await get_tournament(session, tournament_id)


@router.patch("/{tournament_id}", response_model=TournamentRead)
async def update_tournament_endpoint(
    tournament_id: UUID,
    payload: TournamentUpdate,
    session: SessionDependency,
) -> TournamentRead:
    return await update_tournament(
        session,
        tournament_id,
        payload,
    )


@router.post("/{tournament_id}/archive", response_model=TournamentRead)
async def archive_tournament_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentRead:
    return await archive_tournament(
        session,
        tournament_id,
    )


# ---------------------------------------------------------------------------
# Stage 11: competition management
#
# Reads are public. Every mutation requires OrganizerDependency, an interim
# guard until real authentication and per-tournament ownership exist.
# ---------------------------------------------------------------------------

RegistrationStatusFilter = Annotated[
    str | None,
    Query(pattern="^(pending|approved|rejected|withdrawn)$"),
]


@router.get("/presets/{format_code}", response_model=TournamentRules)
async def tournament_preset_endpoint(format_code: FormatCode) -> TournamentRules:
    return rules_preset(format_code)


@router.post("/rules/validate", response_model=TournamentRuleValidationRead)
async def validate_tournament_rules_endpoint(
    payload: TournamentRulesPreview,
) -> TournamentRuleValidationRead:
    return tournament_services.validate_rules_payload(payload.rules)


@router.get("/{tournament_id}/details", response_model=TournamentDetailRead)
async def tournament_details_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentDetailRead:
    return await get_tournament(session, tournament_id)


@router.patch("/{tournament_id}/configuration", response_model=TournamentDetailRead)
async def configure_tournament_endpoint(
    tournament_id: UUID,
    payload: CompetitionConfigUpdate,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentDetailRead:
    return await tournament_services.configure_tournament(
        session,
        tournament_id,
        payload,
        actor_id=actor_id,
    )


@router.get("/{tournament_id}/readiness", response_model=TournamentPreview)
async def tournament_readiness_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentPreview:
    return await tournament_services.validate_tournament_readiness(
        session,
        tournament_id,
    )


@router.post("/{tournament_id}/publication", response_model=TournamentDetailRead)
async def tournament_publication_endpoint(
    tournament_id: UUID,
    payload: TournamentPublishRequest,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentDetailRead:
    return await tournament_services.set_tournament_publication(
        session,
        tournament_id,
        payload.publish,
        actor_id=actor_id,
    )


@router.post("/{tournament_id}/transitions", response_model=TournamentDetailRead)
async def tournament_transition_endpoint(
    tournament_id: UUID,
    payload: TransitionRequest,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentDetailRead:
    return await tournament_services.change_tournament_status(
        session,
        tournament_id,
        payload.target_status,
        payload.reason,
        actor_id=actor_id,
    )


@router.get("/{tournament_id}/transitions", response_model=TournamentTransitionsRead)
async def tournament_transitions_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> TournamentTransitionsRead:
    return await tournament_services.get_tournament_transitions(
        session,
        tournament_id,
    )


@router.get("/{tournament_id}/audit", response_model=list[TournamentAuditRead])
async def tournament_audit_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
    _: OrganizerDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TournamentAuditRead]:
    return await tournament_services.list_tournament_audit(
        session,
        tournament_id,
        limit,
    )


# Rules


@router.post(
    "/{tournament_id}/rules",
    response_model=RuleVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tournament_rules_endpoint(
    tournament_id: UUID,
    payload: RuleVersionCreate,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> RuleVersionRead:
    return await tournament_services.create_tournament_rules(
        session,
        tournament_id,
        payload,
        actor_id=actor_id,
    )


@router.get("/{tournament_id}/rules", response_model=list[RuleVersionRead])
async def list_tournament_rules_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> list[RuleVersionRead]:
    return await tournament_services.list_tournament_rules(session, tournament_id)


@router.get("/{tournament_id}/rules/current", response_model=RuleVersionRead)
async def current_tournament_rules_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> RuleVersionRead:
    return await tournament_services.get_current_tournament_rules(
        session,
        tournament_id,
    )


@router.post("/{tournament_id}/rules/propagate", response_model=RulePropagationRead)
async def propagate_tournament_rules_endpoint(
    tournament_id: UUID,
    payload: RulePropagationRequest,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> RulePropagationRead:
    return await tournament_services.propagate_tournament_rules(
        session,
        tournament_id,
        payload,
        actor_id=actor_id,
    )


@router.get("/{tournament_id}/rules/{version}", response_model=RuleVersionRead)
async def tournament_rule_version_endpoint(
    tournament_id: UUID,
    version: int,
    session: SessionDependency,
) -> RuleVersionRead:
    return await tournament_services.get_tournament_rule_version(
        session,
        tournament_id,
        version,
    )


# Teams


@router.get("/{tournament_id}/teams", response_model=list[TournamentTeamRead])
async def list_tournament_teams_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
    registration_status: RegistrationStatusFilter = None,
) -> list[TournamentTeamRead]:
    return await tournament_services.list_tournament_teams(
        session,
        tournament_id,
        registration_status,
    )


@router.post(
    "/{tournament_id}/teams",
    response_model=TournamentTeamRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_tournament_team_endpoint(
    tournament_id: UUID,
    payload: TournamentTeamRegister,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.register_tournament_team(
        session,
        tournament_id,
        payload,
        actor_id=actor_id,
    )


@router.post(
    "/{tournament_id}/teams/invitations",
    response_model=TournamentTeamRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_tournament_team_endpoint(
    tournament_id: UUID,
    payload: TournamentTeamRegister,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.invite_tournament_team(
        session,
        tournament_id,
        payload,
        actor_id=actor_id,
    )


@router.post(
    "/{tournament_id}/teams/{membership_id}/decision",
    response_model=TournamentTeamRead,
)
async def decide_tournament_registration_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    payload: RegistrationDecision,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.decide_tournament_registration(
        session,
        tournament_id,
        membership_id,
        payload.approve,
        payload.reason,
        actor_id=actor_id,
    )


@router.post(
    "/{tournament_id}/teams/{membership_id}/withdrawal",
    response_model=TournamentTeamRead,
)
async def withdraw_tournament_team_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    payload: TournamentWithdrawalRequest,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.withdraw_tournament_team(
        session,
        tournament_id,
        membership_id,
        payload.reason,
        actor_id=actor_id,
    )


@router.put(
    "/{tournament_id}/teams/{membership_id}/group",
    response_model=TournamentTeamRead,
)
async def assign_tournament_group_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    payload: TournamentGroupAssignment,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.assign_tournament_group(
        session,
        tournament_id,
        membership_id,
        payload.group_id,
        actor_id=actor_id,
    )


@router.put(
    "/{tournament_id}/teams/{membership_id}/captain",
    response_model=TournamentTeamRead,
)
async def set_tournament_captain_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    payload: TournamentCaptainUpdate,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentTeamRead:
    return await tournament_services.set_tournament_captain(
        session,
        tournament_id,
        membership_id,
        payload.player_id,
        actor_id=actor_id,
    )


# Rosters


@router.get(
    "/{tournament_id}/teams/{membership_id}/roster",
    response_model=list[RosterRead],
)
async def list_tournament_roster_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    session: SessionDependency,
) -> list[RosterRead]:
    return await tournament_services.list_tournament_roster(
        session,
        tournament_id,
        membership_id,
    )


@router.post(
    "/{tournament_id}/teams/{membership_id}/roster",
    response_model=RosterRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_tournament_roster_player_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    payload: RosterAdd,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> RosterRead:
    return await tournament_services.add_tournament_roster_player(
        session,
        tournament_id,
        membership_id,
        payload,
        actor_id=actor_id,
    )


@router.delete("/{tournament_id}/teams/{membership_id}/roster/{player_id}")
async def remove_tournament_roster_player_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    player_id: UUID,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> dict[str, bool]:
    return await tournament_services.remove_tournament_roster_player(
        session,
        tournament_id,
        membership_id,
        player_id,
        actor_id=actor_id,
    )


@router.patch(
    "/{tournament_id}/teams/{membership_id}/roster/{player_id}/availability",
    response_model=RosterRead,
)
async def set_roster_availability_endpoint(
    tournament_id: UUID,
    membership_id: UUID,
    player_id: UUID,
    payload: TournamentRosterAvailability,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> RosterRead:
    return await tournament_services.set_roster_availability(
        session,
        tournament_id,
        membership_id,
        player_id,
        payload.is_available,
        payload.reason,
        actor_id=actor_id,
    )


@router.post("/{tournament_id}/rosters/lock")
async def lock_tournament_rosters_endpoint(
    tournament_id: UUID,
    payload: TournamentRosterLockRequest,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> dict[str, int]:
    return await tournament_services.lock_tournament_rosters(
        session,
        tournament_id,
        payload.reason,
        actor_id=actor_id,
    )


# Groups


@router.get("/{tournament_id}/groups", response_model=list[TournamentGroupRead])
async def list_tournament_groups_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> list[TournamentGroupRead]:
    return await tournament_services.list_tournament_groups(session, tournament_id)


@router.post(
    "/{tournament_id}/groups",
    response_model=TournamentGroupRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tournament_group_endpoint(
    tournament_id: UUID,
    payload: GroupCreate,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentGroupRead:
    return await tournament_services.create_tournament_group(
        session,
        tournament_id,
        payload.name,
        payload.sort_order,
        actor_id=actor_id,
    )


@router.delete("/{tournament_id}/groups/{group_id}")
async def delete_tournament_group_endpoint(
    tournament_id: UUID,
    group_id: UUID,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> dict[str, bool]:
    return await tournament_services.delete_tournament_group(
        session,
        tournament_id,
        group_id,
        actor_id=actor_id,
    )


# Venues


@router.get("/{tournament_id}/venues", response_model=list[TournamentVenueRead])
async def list_tournament_venues_endpoint(
    tournament_id: UUID,
    session: SessionDependency,
) -> list[TournamentVenueRead]:
    return await tournament_services.list_tournament_venues(session, tournament_id)


@router.post(
    "/{tournament_id}/venues",
    response_model=TournamentVenueRead,
    status_code=status.HTTP_201_CREATED,
)
async def assign_tournament_venue_endpoint(
    tournament_id: UUID,
    payload: VenueAssign,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> TournamentVenueRead:
    return await tournament_services.assign_tournament_venue(
        session,
        tournament_id,
        payload.venue_id,
        actor_id=actor_id,
    )


@router.delete("/{tournament_id}/venues/{venue_id}")
async def remove_tournament_venue_endpoint(
    tournament_id: UUID,
    venue_id: UUID,
    session: SessionDependency,
    actor_id: OrganizerDependency,
) -> dict[str, bool]:
    return await tournament_services.remove_tournament_venue(
        session,
        tournament_id,
        venue_id,
        actor_id=actor_id,
    )
