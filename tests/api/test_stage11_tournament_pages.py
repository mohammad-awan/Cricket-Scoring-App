from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app


SECTIONS = ("overview", "identity", "rules", "teams", "squads", "venues")


async def _get(path: str):
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/competitions", "/competitions/new"])
async def test_tournament_list_and_wizard_pages_render(path: str) -> None:
    response = await _get(path)

    assert response.status_code == 200
    assert "tournament-common.js" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("section", SECTIONS)
async def test_tournament_workspace_sections_render(section: str) -> None:
    tournament_id = uuid4()

    response = await _get(f"/competitions/{tournament_id}/{section}")

    assert response.status_code == 200
    assert f'data-section="{section}"' in response.text
    assert f'class="t-tab active" href="/competitions/{tournament_id}/{section}"' in response.text


@pytest.mark.asyncio
async def test_unknown_workspace_section_is_404() -> None:
    response = await _get(f"/competitions/{uuid4()}/fixtures")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pages_do_not_shadow_the_json_api() -> None:
    # /tournaments stays the JSON API; pages live under /competitions.
    response = await _get("/tournaments/presets/t10")

    assert response.status_code == 200
    assert response.json()["overs_per_innings"] == 10
