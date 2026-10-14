"""Upload guards that run before any database access."""

from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import get_settings
from app.main import create_app


async def _put(path: str, body: bytes, content_type: str = "image/png"):
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        return await client.put(path, content=body, headers={"Content-Type": content_type})


@pytest.mark.asyncio
async def test_unknown_asset_kind_is_404() -> None:
    response = await _put(f"/tournaments/{uuid4()}/assets/banner", b"\x89PNG\r\n\x1a\n")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_oversized_upload_is_413_before_reaching_storage() -> None:
    too_big = b"\x89PNG\r\n\x1a\n" + b"\x00" * get_settings().tournament_asset_max_bytes

    response = await _put(f"/tournaments/{uuid4()}/assets/logo", too_big)

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_route_documents_image_body() -> None:
    schema = create_app().openapi()
    body = schema["paths"]["/tournaments/{tournament_id}/assets/{kind}"]["put"]["requestBody"]

    assert set(body["content"]) == {"image/png", "image/jpeg", "image/webp"}
