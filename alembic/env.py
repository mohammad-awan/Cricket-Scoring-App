from __future__ import annotations

import asyncio
import selectors
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base

# Import every SQLAlchemy model so Alembic can detect its tables.
# Add future model imports here as the project grows.
from app.models import *  # noqa: F401, F403


# Alembic Config object, connected to alembic.ini
config = context.config


# Configure Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Metadata used by Alembic migrations
target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Load the Supabase PostgreSQL URL from the application settings.
    Supports both SecretStr and normal string values.
    """
    settings = get_settings()
    database_url = settings.database_url

    if hasattr(database_url, "get_secret_value"):
        return database_url.get_secret_value()

    return str(database_url)



def run_migrations_offline() -> None:
    """
    Run migrations without creating a database connection.
    """
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """
    Run Alembic migrations using an existing SQLAlchemy connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create the asynchronous SQLAlchemy engine and run migrations.
    """
    configuration = config.get_section(config.config_ini_section) or {}

    # Override the placeholder URL from alembic.ini with DATABASE_URL
    # loaded from the project's .env file.
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def create_windows_selector_loop() -> asyncio.AbstractEventLoop:
    """
    Psycopg async connections require SelectorEventLoop on Windows.
    This is needed when running with modern Python versions such as 3.14.
    """
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    return loop


def run_migrations_online() -> None:
    """
    Run migrations using a live asynchronous database connection.
    """
    if sys.platform == "win32":
        asyncio.run(
            run_async_migrations(),
            loop_factory=create_windows_selector_loop,
        )
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()