import os

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


os.environ.setdefault("ENVIRONMENT", "test")


