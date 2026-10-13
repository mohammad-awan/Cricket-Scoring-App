from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))


def asset_version(path: str) -> str:
    """Cache-busting token that changes whenever a static file changes."""
    try:
        return str(int((PROJECT_ROOT / "static" / path).stat().st_mtime))
    except OSError:
        return "0"


templates.env.globals["asset_version"] = asset_version
router = APIRouter(include_in_schema=False)


MASTER_DATA_RESOURCES = {
    "teams",
    "players",
    "venues",
    "tournaments",
}


@router.get("/app")
async def app_entry() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


@router.get("/master-data/{resource}")
async def master_data_page(request: Request, resource: str):
    if resource not in MASTER_DATA_RESOURCES:
        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="master_data.html",
        context={
            "resource": resource,
        },
    )


@router.get("/match-setup")
async def matches_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="matches.html",
        context={},
    )


@router.get("/match-setup/{match_id}")
async def match_setup_page(request: Request, match_id: str):
    return templates.TemplateResponse(
        request=request,
        name="match_setup.html",
        context={
            "match_id": match_id,
        },
    )


@router.get("/live-scoring/{match_id}")
async def live_scoring_page(request: Request, match_id: str):
    return templates.TemplateResponse(
        request=request,
        name="live_scoring.html",
        context={
            "match_id": match_id
        }

    )


@router.get("/scorecard/{match_id}")
async def scorecard_page(request: Request, match_id: str):
    return templates.TemplateResponse(
        request=request,
        name="scorecard.html",
        context={
            "match_id": match_id,
        },
    )


@router.get("/live-viewer/{match_id}")
async def live_viewer_page(request: Request, match_id: str):
    return templates.TemplateResponse(
        request=request,
        name="live_viewer.html",
        context={"match_id": match_id}
    )


@router.get("/player-profile/{player_id}")
async def player_detail_page(request: Request, player_id: str):
    return templates.TemplateResponse(
        request=request,
        name="player_detail.html",
        context={
            "player_id":
                player_id,
        },
    )


TOURNAMENT_SECTIONS = {
    "overview",
    "identity",
    "rules",
    "teams",
    "squads",
    "venues",
}


@router.get("/competitions")
async def tournaments_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="tournaments.html",
        context={},
    )


@router.get("/competitions/new")
async def tournament_create_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="tournament_wizard.html",
        context={"tournament_id": ""},
    )


@router.get("/competitions/{tournament_id}/edit")
async def tournament_edit_page(request: Request, tournament_id: str):
    return templates.TemplateResponse(
        request=request,
        name="tournament_wizard.html",
        context={"tournament_id": tournament_id},
    )


@router.get("/competitions/{tournament_id}")
@router.get("/competitions/{tournament_id}/{section}")
async def tournament_detail_page(
    request: Request,
    tournament_id: str,
    section: str = "overview",
):
    if section not in TOURNAMENT_SECTIONS:
        raise HTTPException(status_code=404, detail="Page not found")

    return templates.TemplateResponse(
        request=request,
        name="tournament_detail.html",
        context={
            "tournament_id": tournament_id,
            "section": section,
        },
    )
