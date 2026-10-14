from fastapi import APIRouter
from app.api.routes.health import router as health_router
from app.api.routes.players import router as players_router
from app.api.routes.teams import router as teams_router
from app.api.routes.tournaments import router as tournaments_router
from app.api.routes.tournament_series import router as tournament_series_router
from app.api.routes.venues import router as venues_router
from app.api.routes.match_setup import router as match_setup_router
from app.api.routes.scoring import router as scoring_router
from app.api.routes.scorecard import router as scorecard_router
from app.api.routes.team_squads import router as team_squads_router
from app.api.routes.realtime import router as realtime_router
from app.api.routes.player_profile import router as player_profile_router


api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(teams_router)
api_router.include_router(players_router)
api_router.include_router(venues_router)
api_router.include_router(tournaments_router)
api_router.include_router(tournament_series_router)
api_router.include_router(match_setup_router)
api_router.include_router(scoring_router)
api_router.include_router(scorecard_router)
api_router.include_router(realtime_router)
api_router.include_router(player_profile_router)
api_router.include_router(team_squads_router)
