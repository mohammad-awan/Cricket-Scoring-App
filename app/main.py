from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import close_database
from app.web.router import router as web_router


BASE_DIR = Path(__file__).resolve().parent.parent

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()

    try:
        yield

    finally:
        await close_database()


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    application.mount(
        "/static",
        StaticFiles(
            directory=str(
                BASE_DIR / "static"
            )
        ),
        name="static",
    )

    application.include_router(api_router)
    application.include_router(web_router)
    register_exception_handlers(application)

    @application.get("/")
    def index() -> dict[str, str]:
        return {
            "Project Name": settings.app_name,
            "Date": date.today().isoformat(),
        }

    return application


app = create_app()