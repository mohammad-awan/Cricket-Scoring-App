"""UI-facing fixture operations. Every mutation commits once or rolls back."""
from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.fixtures import handle_fixture_error
from app.db.session import get_db_session
from app.schemas.fixture_planning import (
    FixtureAction, FixtureConfirm, FixtureEditBatch, FixturePlanRequest, FixturePlanSave, FixtureRegenerate,
)
from app.schemas.fixtures import FixtureChangeAuditResponse
from app.services.fixture import FixtureServiceError
from app.services.fixture_planning import FixturePlanningService

router = APIRouter(prefix="/fixtures", tags=["Fixture planning"])


async def execute(session, operation, write=False):
    try:
        result = jsonable_encoder(await operation)
        if write:
            await session.commit()
        return result
    except Exception as error:
        if write:
            await session.rollback()
        if isinstance(error, FixtureServiceError):
            handle_fixture_error(error)
        raise


@router.get("/tournaments/{tournament_id}/workspace")
async def workspace(tournament_id: UUID, generation_run_id: UUID | None = None, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).workspace(tournament_id, generation_run_id))


@router.post("/tournaments/{tournament_id}/generate-preview")
async def preview(tournament_id: UUID, payload: FixturePlanRequest, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).preview(tournament_id, payload))


@router.post("/tournaments/{tournament_id}/plans", status_code=201)
async def save(tournament_id: UUID, payload: FixturePlanSave, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).save(tournament_id, payload), True)


@router.get("/generations/{run_id}/explain")
@router.get("/generations/{run_id}/bracket-tree")
@router.post("/generations/{run_id}/validate")
async def validate(run_id: UUID, session: AsyncSession = Depends(get_db_session)):
    service = FixturePlanningService(session)
    async def report():
        run, _, rows = await service.load(run_id)
        return await service.report(run, rows)
    return await execute(session, report())


@router.post("/generations/{run_id}/edits")
async def edit(run_id: UUID, payload: FixtureEditBatch, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).edit(run_id, payload), True)


@router.post("/generations/{run_id}/confirm")
async def publish(run_id: UUID, payload: FixtureConfirm, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).publish(run_id, payload.expected_versions, payload.reason), True)


@router.post("/{fixture_id}/actions")
async def action(fixture_id: UUID, payload: FixtureAction, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).action(fixture_id, payload), True)


@router.post("/generations/{run_id}/regenerate-unplayed")
async def regenerate(run_id: UUID, payload: FixtureRegenerate, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).regenerate(run_id, payload), True)


@router.post("/generations/{run_id}/progress")
async def progress(run_id: UUID, session: AsyncSession = Depends(get_db_session)):
    return await execute(session, FixturePlanningService(session).progress(run_id), True)


@router.get("/{fixture_id}/history")
async def history(fixture_id: UUID, session: AsyncSession = Depends(get_db_session)):
    service = FixturePlanningService(session)
    async def read():
        return [FixtureChangeAuditResponse.model_validate(row) for row in await service.repo.audit(fixture_id)]
    return await execute(session, read())
