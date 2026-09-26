import asyncio
import sys
import os

import pytest

# Unit/API tests never connect to this placeholder.
# Live tests read the real URL from .env.

if os.getenv("RUN_LIVE_DB_TESTS") != "1":
    os.environ.setdefault(
        "DATABASE_URL",
        (
            "postgresql+psycopg://"
            "postgres:postgres@localhost:5432/postgres"
        ),
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()

    return asyncio.DefaultEventLoopPolicy()



os.environ.setdefault("ENVIRONMENT", "test")


