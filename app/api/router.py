from fastapi import APIRouter
from app.api.routes.health import router as health_router
from app.api.routes.master_data import router as master_data_router
from app.api.routes.match_setup import router as match_setup_router
from app.api.routes.team_squads import router as team_squads_router



api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(master_data_router)
api_router.include_router(match_setup_router)
api_router.include_router(team_squads_router)