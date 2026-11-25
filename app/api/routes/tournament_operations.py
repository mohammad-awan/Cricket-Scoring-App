from __future__ import annotations
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.api.dependencies import OrganizerDependency, SessionDependency
from app.models.entities.fixtures import FixtureGenerationRun
from app.services.realtime import publish_tournament_event, tournament_connections
from app.services.tournament_closeout import (
    REOPENING_POLICY,
    closeout_readiness,
    finalize_tournament,
    official_record,
    reopen_tournament,
)
from app.services.tournament_decisions import list_decisions
from app.services.tournament_operations import (
    get_tournament_overview,
    operations_board,
    tournament_bracket,
    tournament_calendar,
    tournament_groups,
    tournament_live,
    tournament_results,
)
from app.services.tournament_qualification import tournament_qualification
from app.services.tournament_results import (
    current_dispositions,
    record_fixture_disposition,
    revoke_fixture_disposition,
)
from app.services.tournament_standings import (
    active_adjudications,
    active_bonuses,
    calculate_tournament_standings,
    record_points_bonus,
    record_standings_adjudication,
    revoke_points_bonus,
    revoke_standings_adjudication,
)
from app.services.tournaments import get_tournament, tournament_transaction


router = APIRouter(prefix="/tournaments", tags=["Tournament Operations"])


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=2000)


class TournamentReopenRequest(ReasonRequest):
    pass


class DispositionRequest(ReasonRequest):
    outcome: Literal["walkover", "no_result", "abandoned", "cancelled", "knockout_advancement"]
    winner_team_id: UUID | None = None


class AdjudicationRequest(ReasonRequest):
    group_key: str = Field(min_length=1, max_length=120)
    team_ids: list[UUID] = Field(min_length=2, max_length=64)
    method: Literal["committee", "drawing_of_lots", "competition_rule"] = "committee"


class AdjudicationRevocation(ReasonRequest):
    group_key: str = Field(min_length=1, max_length=120)


class BonusRequest(ReasonRequest):
    team_id: UUID
    points: int = Field(ge=1, le=100)
    match_id: UUID | None = None


# ---------------------------------------------------------------------------
# Headquarters and live operations
# ---------------------------------------------------------------------------


@router.get("/{tournament_id}/overview")
async def tournament_overview(tournament_id: UUID, session: SessionDependency):
    return await get_tournament_overview(session, tournament_id)


@router.get("/{tournament_id}/live")
async def tournament_live_matches(tournament_id: UUID, session: SessionDependency):
    return await tournament_live(session, tournament_id)


@router.get("/{tournament_id}/results")
async def tournament_result_list(tournament_id: UUID, session: SessionDependency):
    return await tournament_results(session, tournament_id)


@router.get("/{tournament_id}/calendar")
async def tournament_fixture_calendar(
    tournament_id: UUID,
    session: SessionDependency,
    team_id: UUID | None = None,
    venue_id: UUID | None = None,
):
    return await tournament_calendar(session, tournament_id, team_id=team_id, venue_id=venue_id)


@router.get("/{tournament_id}/operations")
async def tournament_operations_board(tournament_id: UUID, session: SessionDependency, organizer: OrganizerDependency):
    return await operations_board(session, tournament_id)


@router.websocket("/{tournament_id}/live/ws")
async def tournament_live_websocket(tournament_id: UUID, websocket: WebSocket) -> None:
    await tournament_connections.connect(tournament_id, websocket)
    try:
        await websocket.send_json({"event_type": "connected", "tournament_id": str(tournament_id), "payload": {}})
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await tournament_connections.disconnect(tournament_id, websocket)


# ---------------------------------------------------------------------------
# Standings, groups, qualification, bracket
# ---------------------------------------------------------------------------


@router.get("/{tournament_id}/standings")
async def tournament_standings(tournament_id: UUID, session: SessionDependency):
    return await calculate_tournament_standings(session, tournament_id)


@router.get("/{tournament_id}/group-tables")
async def tournament_group_tables(tournament_id: UUID, session: SessionDependency):
    return await tournament_groups(session, tournament_id)


@router.get("/{tournament_id}/qualification")
async def tournament_qualification_status(
    tournament_id: UUID,
    session: SessionDependency,
    top_k: int | None = Query(default=None, ge=1, le=128),
    best_rank: int | None = Query(default=None, ge=1, le=64),
    best_count: int = Query(default=0, ge=0, le=64),
):
    return await tournament_qualification(session, tournament_id, top_k, best_rank=best_rank, best_count=best_count)


@router.get("/{tournament_id}/bracket")
async def tournament_bracket_view(tournament_id: UUID, session: SessionDependency):
    return await tournament_bracket(session, tournament_id)


@router.post("/{tournament_id}/bracket/resolve")
async def resolve_tournament_bracket(tournament_id: UUID, session: SessionDependency, organizer: OrganizerDependency):
    """Recompute bracket slots from official results (idempotent, atomic)."""

    from app.services.fixture_planning import FixturePlanningService

    async with tournament_transaction(session, "Bracket resolution"):
        await get_tournament(session, tournament_id)
        runs = (
            await session.scalars(
                select(FixtureGenerationRun.id).where(
                    FixtureGenerationRun.tournament_id == tournament_id,
                    FixtureGenerationRun.status == "published",
                )
            )
        ).all()
        service = FixturePlanningService(session)
        results = [{"generation_run_id": run_id, **await service.progress(run_id)} for run_id in runs]

    await publish_tournament_event(tournament_id, "bracket_updated", {"runs": results})
    return {"tournament_id": tournament_id, "runs": results}


# ---------------------------------------------------------------------------
# Result dispositions and standings decisions
# ---------------------------------------------------------------------------


@router.get("/{tournament_id}/dispositions")
async def list_fixture_dispositions(tournament_id: UUID, session: SessionDependency):
    return list((await current_dispositions(session, tournament_id)).values())


@router.post("/{tournament_id}/fixtures/{fixture_id}/disposition")
async def record_disposition(
    tournament_id: UUID,
    fixture_id: UUID,
    payload: DispositionRequest,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await record_fixture_disposition(
        session, tournament_id, fixture_id,
        outcome=payload.outcome, winner_team_id=payload.winner_team_id, reason=payload.reason,
    )
    await publish_tournament_event(tournament_id, "result_committed", {"fixture_id": fixture_id, "outcome": payload.outcome})
    return result


@router.post("/{tournament_id}/fixtures/{fixture_id}/disposition/revoke")
async def revoke_disposition(
    tournament_id: UUID,
    fixture_id: UUID,
    payload: ReasonRequest,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await revoke_fixture_disposition(session, tournament_id, fixture_id, reason=payload.reason)
    await publish_tournament_event(tournament_id, "result_committed", {"fixture_id": fixture_id, "outcome": None})
    return result


@router.get("/{tournament_id}/standings/adjudications")
async def list_standings_adjudications(tournament_id: UUID, session: SessionDependency):
    return list((await active_adjudications(session, tournament_id)).values())


@router.post("/{tournament_id}/standings/adjudications")
async def adjudicate_standings(
    tournament_id: UUID,
    payload: AdjudicationRequest,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await record_standings_adjudication(
        session, tournament_id, payload.group_key, payload.team_ids, payload.reason, method=payload.method
    )
    await publish_tournament_event(tournament_id, "standings_changed", {"group_key": payload.group_key})
    return result


@router.post("/{tournament_id}/standings/adjudications/revoke")
async def revoke_adjudication(
    tournament_id: UUID,
    payload: AdjudicationRevocation,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await revoke_standings_adjudication(session, tournament_id, payload.group_key, payload.reason)
    await publish_tournament_event(tournament_id, "standings_changed", {"group_key": payload.group_key})
    return result


@router.get("/{tournament_id}/standings/bonuses")
async def list_points_bonuses(tournament_id: UUID, session: SessionDependency):
    return await active_bonuses(session, tournament_id)


@router.post("/{tournament_id}/standings/bonuses")
async def add_points_bonus(tournament_id: UUID, payload: BonusRequest, session: SessionDependency, organizer: OrganizerDependency):
    result = await record_points_bonus(
        session, tournament_id, payload.team_id, payload.points, payload.reason, match_id=payload.match_id
    )
    await publish_tournament_event(tournament_id, "standings_changed", {"bonus_id": result["bonus_id"]})
    return result


@router.post("/{tournament_id}/standings/bonuses/{bonus_id}/revoke")
async def remove_points_bonus(
    tournament_id: UUID,
    bonus_id: UUID,
    payload: ReasonRequest,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    result = await revoke_points_bonus(session, tournament_id, bonus_id, payload.reason)
    await publish_tournament_event(tournament_id, "standings_changed", {"bonus_id": bonus_id})
    return result


# ---------------------------------------------------------------------------
# Finalization, reopening and history
# ---------------------------------------------------------------------------


@router.get("/{tournament_id}/closeout/readiness")
async def tournament_closeout_readiness(tournament_id: UUID, session: SessionDependency):
    return await closeout_readiness(session, tournament_id)


@router.post("/{tournament_id}/finalize")
async def finalize_tournament_operation(tournament_id: UUID, session: SessionDependency, organizer: OrganizerDependency):
    closeout = await finalize_tournament(session, tournament_id)
    await publish_tournament_event(tournament_id, "tournament_finalized", {"champion_team_id": closeout.champion_team_id})
    return {
        "tournament_id": closeout.tournament_id,
        "champion_team_id": closeout.champion_team_id,
        "revision": closeout.revision,
        "is_frozen": closeout.is_frozen,
        "finalized_at": closeout.finalized_at,
        "snapshot": closeout.snapshot,
    }


@router.post("/{tournament_id}/reopen")
async def reopen_tournament_operation(
    tournament_id: UUID,
    payload: TournamentReopenRequest,
    session: SessionDependency,
    organizer: OrganizerDependency,
):
    closeout = await reopen_tournament(session, tournament_id, payload.reason)
    await publish_tournament_event(tournament_id, "tournament_reopened", {"reason": payload.reason})
    return {
        "tournament_id": closeout.tournament_id,
        "revision": closeout.revision,
        "is_frozen": closeout.is_frozen,
        "reopened_at": closeout.reopened_at,
        "reopen_reason": closeout.reopen_reason,
        "reopening_policy": REOPENING_POLICY,
    }


@router.get("/{tournament_id}/official-record")
async def tournament_official_record(tournament_id: UUID, session: SessionDependency):
    return await official_record(session, tournament_id)


@router.get("/{tournament_id}/decisions")
async def tournament_decision_history(tournament_id: UUID, session: SessionDependency, organizer: OrganizerDependency):
    return [
        {
            "id": decision.id,
            "decision_type": decision.decision_type,
            "subject_id": decision.subject_id,
            "actor_id": decision.actor_id,
            "reason": decision.reason,
            "payload": decision.payload,
            "created_at": decision.created_at,
        }
        for decision in await list_decisions(session, tournament_id)
    ]
