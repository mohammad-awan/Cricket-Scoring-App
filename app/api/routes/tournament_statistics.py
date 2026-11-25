from __future__ import annotations
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from app.api.dependencies import SessionDependency
from app.models import Tournament, TournamentSeries
from app.services.tournament_closeout import series_history
from app.services.tournament_exports import make_csv
from app.services.tournament_statistics import (
    compute_player_profile,
    compute_player_statistics,
    compute_records,
    compute_team_statistics,
    series_player_statistics,
    tournament_statistics_data,
)


router = APIRouter(prefix="/tournaments", tags=["Tournament Statistics"])
series_router = APIRouter(prefix="/tournament-series", tags=["Tournament Statistics"])


async def ensure_tournament(session, tournament_id: UUID) -> None:
    if await session.get(Tournament, tournament_id) is None:
        raise HTTPException(status_code=404, detail="Tournament not found")


def _limit(rows: list[dict], limit: int | None, qualified_only: bool) -> list[dict]:
    rows = [row for row in rows if row.get("qualifies", True)] if qualified_only else rows
    return rows[:limit] if limit else rows


@router.get("/{tournament_id}/leaderboards")
async def leaderboards(
    tournament_id: UUID,
    session: SessionDependency,
    team_id: UUID | None = None,
    min_innings: int = Query(default=0, ge=0, le=100),
    min_balls: int = Query(default=0, ge=0, le=10_000),
    qualified_only: bool = False,
    limit: int | None = Query(default=None, ge=1, le=500),
):
    """Orange-cap (batting), purple-cap (bowling) and fielding leaderboards."""

    await ensure_tournament(session, tournament_id)
    stats = compute_player_statistics(
        await tournament_statistics_data(session, tournament_id), team_id=team_id, min_innings=min_innings, min_balls=min_balls
    )
    for key in ("batting", "bowling", "fielding"):
        stats[key] = _limit(stats[key], limit, qualified_only)
    return {"tournament_id": tournament_id, "team_id": team_id, **stats}


@router.get("/{tournament_id}/leaderboards/export")
async def export_leaderboard(
    tournament_id: UUID,
    session: SessionDependency,
    category: Literal["batting", "bowling", "fielding"] = "batting",
    min_innings: int = Query(default=0, ge=0),
    min_balls: int = Query(default=0, ge=0),
):
    await ensure_tournament(session, tournament_id)
    stats = compute_player_statistics(
        await tournament_statistics_data(session, tournament_id), min_innings=min_innings, min_balls=min_balls
    )
    rows = [{**row, "teams": [team["team_name"] for team in row["teams"]]} for row in stats[category]]
    return Response(
        content=make_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{category}_leaderboard.csv"'},
    )


@router.get("/{tournament_id}/player-stats/{player_id}")
async def player_tournament_statistics(tournament_id: UUID, player_id: UUID, session: SessionDependency):
    await ensure_tournament(session, tournament_id)
    profile = compute_player_profile(await tournament_statistics_data(session, tournament_id), player_id)
    if not profile["matches"] and profile["batting"] is None and profile["bowling"] is None:
        raise HTTPException(status_code=404, detail="Player has no official appearances in this tournament")
    return {"tournament_id": tournament_id, **profile}


@router.get("/{tournament_id}/team-stats")
async def team_tournament_statistics(tournament_id: UUID, session: SessionDependency):
    await ensure_tournament(session, tournament_id)
    return {"tournament_id": tournament_id, "teams": compute_team_statistics(await tournament_statistics_data(session, tournament_id))}


@router.get("/{tournament_id}/team-stats/{team_id}")
async def single_team_statistics(tournament_id: UUID, team_id: UUID, session: SessionDependency):
    await ensure_tournament(session, tournament_id)
    data = await tournament_statistics_data(session, tournament_id)
    team = next((row for row in compute_team_statistics(data) if row["team_id"] == team_id), None)
    if team is None:
        raise HTTPException(status_code=404, detail="Team has no official results in this tournament")
    players = compute_player_statistics(data, team_id=team_id)
    return {"tournament_id": tournament_id, **team, "batting": players["batting"], "bowling": players["bowling"], "fielding": players["fielding"]}


@router.get("/{tournament_id}/records")
async def tournament_records(tournament_id: UUID, session: SessionDependency, limit: int = Query(default=5, ge=1, le=50)):
    await ensure_tournament(session, tournament_id)
    return {"tournament_id": tournament_id, **compute_records(await tournament_statistics_data(session, tournament_id), limit)}


@series_router.get("/{series_id}/leaderboards")
async def series_leaderboards(
    series_id: UUID,
    session: SessionDependency,
    season: str | None = Query(default=None, max_length=40),
    min_innings: int = Query(default=0, ge=0),
    min_balls: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=500),
):
    """Cross-season leaderboards: each player counted once across editions."""

    if await session.get(TournamentSeries, series_id) is None:
        raise HTTPException(status_code=404, detail="Tournament series not found")
    stats = await series_player_statistics(session, series_id, season=season, min_innings=min_innings, min_balls=min_balls)
    for key in ("batting", "bowling", "fielding"):
        stats[key] = _limit(stats[key], limit, False)
    return stats


@series_router.get("/{series_id}/history")
async def series_edition_history(series_id: UUID, session: SessionDependency):
    """Archived editions with their frozen champions and awards."""

    if await session.get(TournamentSeries, series_id) is None:
        raise HTTPException(status_code=404, detail="Tournament series not found")
    return await series_history(session, series_id)
