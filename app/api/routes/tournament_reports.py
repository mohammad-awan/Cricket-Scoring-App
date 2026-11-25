from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response
from app.api.dependencies import SessionDependency
from app.services.tournament_exports import (
    FIXTURE_COLUMNS,
    SCORECARD_COLUMNS,
    SQUAD_COLUMNS,
    STANDINGS_COLUMNS,
    fixtures_rows,
    make_csv,
    squad_rows,
    standings_rows,
)
from app.services.tournament_reports import build_tournament_report, render_report_html
from app.services.tournament_statistics import compute_team_statistics, tournament_statistics_data
from app.services.tournaments import get_tournament


router = APIRouter(prefix="/tournaments", tags=["Tournament Reports"])


def csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{tournament_id}/report")
async def get_tournament_report(tournament_id: UUID, session: SessionDependency):
    """Tournament summary (JSON)."""

    return await build_tournament_report(session, tournament_id)


@router.get("/{tournament_id}/report/print", response_class=HTMLResponse)
async def get_printable_tournament_report(tournament_id: UUID, session: SessionDependency):
    return HTMLResponse(render_report_html(await build_tournament_report(session, tournament_id)))


@router.get("/{tournament_id}/report/team-records.csv")
async def export_team_records(tournament_id: UUID, session: SessionDependency):
    await get_tournament(session, tournament_id)
    rows = [{key: value for key, value in row.items() if key != "form"}
            for row in compute_team_statistics(await tournament_statistics_data(session, tournament_id))]
    return csv_response(make_csv(rows), "team_records.csv")


@router.get("/{tournament_id}/export/fixtures.csv")
async def export_fixtures(tournament_id: UUID, session: SessionDependency):
    return csv_response(make_csv(await fixtures_rows(session, tournament_id), FIXTURE_COLUMNS), "fixtures.csv")


@router.get("/{tournament_id}/export/standings.csv")
async def export_standings(tournament_id: UUID, session: SessionDependency):
    return csv_response(make_csv(await standings_rows(session, tournament_id), STANDINGS_COLUMNS), "standings.csv")


@router.get("/{tournament_id}/export/scorecards.csv")
async def export_scorecard_links(tournament_id: UUID, session: SessionDependency):
    rows = [row for row in await fixtures_rows(session, tournament_id) if row["match_id"]]
    return csv_response(make_csv(rows, SCORECARD_COLUMNS), "scorecard_links.csv")


@router.get("/{tournament_id}/export/squads.csv")
async def export_squads(tournament_id: UUID, session: SessionDependency):
    await get_tournament(session, tournament_id)
    return csv_response(make_csv(await squad_rows(session, tournament_id), SQUAD_COLUMNS), "squads.csv")
