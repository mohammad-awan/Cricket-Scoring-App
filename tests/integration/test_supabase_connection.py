import os
import pytest
from sqlalchemy import text
from app.db.session import AsyncSessionFactory



pytestmark = pytest.mark.integration



@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_TESTS") != "1",
    reason=(
        "Set RUN_LIVE_DB_TESTS=1 to test "
        "the configured Supabase database"
    ),
)
async def test_real_supabase_connection() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.scalar(
            text("SELECT 1")
        )
    assert result == 1



