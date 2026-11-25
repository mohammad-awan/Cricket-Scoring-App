from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.models.entities.fixtures import Fixture, FixtureGenerationRun
from app.schemas.fixtures import (
    FixtureGenerateRequest,
    FixtureGenerationResultResponse,
    FixtureListResponse,
    FixturePublishRequest,
    FixturePublishResponse,
    FixtureResponse,
    FixtureUpdateRequest,
)
from app.services.fixture import (
    FixtureService,
    FixtureValidationError,
    FixtureNotFoundError,
    FixtureConflictError,
)
from app.services.tournament_bracket_review import review_bracket
from app.models.entities.fixtures import FixtureBracketDependency
from app.services.tournament_bracket import advance_bracket_dependency, BracketAdvancementError, BracketAdvancementConflict
import csv
import io
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/fixtures", tags=["Tournament Fixtures"])


# ---------------------------------------
# SERVICE DEPENDENCY
# ---------------------------------------

def get_fixture_service(session: AsyncSession = Depends(get_db_session)):
    return FixtureService(session)


# ---------------------------------------
# ERROR HANDLING
# ---------------------------------------

def handle_fixture_error(error: Exception):
    if isinstance(error, FixtureNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(error, FixtureConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, FixtureValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    raise error


# ---------------------------------------
# GENERATE TOURNAMENT FIXTURES
# ---------------------------------------

@router.post(
    "/tournaments/{tournament_id}/generate",
    response_model=FixtureGenerationResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_tournament_fixtures(
    tournament_id: UUID,
    payload: FixtureGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    service = FixtureService(session)

    try:
        result = await service.generate_fixtures(
            tournament_id=tournament_id,
            method=payload.method,
            configuration=payload.configuration,
            seed=payload.seed,
        )

        await session.commit()

        return FixtureGenerationResultResponse(
            generation_run_id=result.generation_run_id,
            tournament_id=result.tournament_id,
            fixture_count=result.fixture_count,
            round_count=result.round_count,
        )

    except (
        FixtureValidationError,
        FixtureNotFoundError,
        FixtureConflictError,
    ) as error:
        await session.rollback()
        handle_fixture_error(error)

    except Exception:
        await session.rollback()
        raise


# ---------------------------------------
# LIST TOURNAMENT FIXTURES
# ---------------------------------------

@router.get(
    "/tournaments/{tournament_id}",
    response_model=FixtureListResponse,
)
async def list_tournament_fixtures(
    tournament_id: UUID,
    generation_run_id: UUID | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: AsyncSession = Depends(get_db_session),
):
    conditions = [
        Fixture.tournament_id == tournament_id,
    ]

    if generation_run_id is not None:
        conditions.append(
            Fixture.generation_run_id == generation_run_id
        )

    total = await session.scalar(
        select(
            func.count(Fixture.id)
        ).where(
            *conditions
        )
    )

    result = await session.scalars(
        select(Fixture)
        .where(*conditions)
        .order_by(
            Fixture.generation_run_id,
            Fixture.fixture_number,
        )
        .limit(limit)
        .offset(offset)
    )

    fixtures = list(result.all())

    return FixtureListResponse(
        tournament_id=tournament_id,
        total=total or 0,
        fixtures=[
            FixtureResponse.model_validate(fixture)
            for fixture in fixtures
        ],
    )


# ---------------------------------------
# GET SINGLE FIXTURE
# ---------------------------------------

@router.get(
    "/{fixture_id}",
    response_model=FixtureResponse,
)
async def get_fixture(fixture_id: UUID, session: AsyncSession = Depends(get_db_session)):
    fixture = await session.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fixture not found.",
        )

    return FixtureResponse.model_validate(fixture)


# ---------------------------------------
# PUBLISH FIXTURE GENERATION
# ---------------------------------------

@router.post(
    "/generations/{generation_run_id}/publish",
    response_model=FixturePublishResponse,
)
async def publish_fixture_generation(
    generation_run_id: UUID,
    payload: FixturePublishRequest,
    session: AsyncSession = Depends(get_db_session),
):
    service = FixtureService(session)

    try:
        published_count = await service.publish_generation(
            generation_run_id=generation_run_id,
            expected_fixture_count=payload.expected_fixture_count,
        )

        await session.commit()

        return FixturePublishResponse(
            generation_run_id=generation_run_id,
            published_count=published_count,
            status="published",
        )

    except (
        FixtureValidationError,
        FixtureNotFoundError,
        FixtureConflictError,
    ) as error:
        await session.rollback()
        handle_fixture_error(error)

    except Exception:
        await session.rollback()
        raise


# ---------------------------------------
# UPDATE FIXTURE
# ---------------------------------------

@router.patch(
    "/{fixture_id}",
    response_model=FixtureResponse,
)
async def update_fixture(
    fixture_id: UUID,
    payload: FixtureUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    service = FixtureService(session)

    changes = payload.model_dump(
        exclude_unset=True,
        exclude={"expected_version"},
    )

    try:
        await service.update_fixture(
            fixture_id=fixture_id,
            expected_version=payload.expected_version,
            changes=changes,
        )

        # Reload before committing, so response validation
        # failures do not occur after a successful commit.
        fixture = await session.get(
            Fixture,
            fixture_id,
            populate_existing=True,
        )

        if fixture is None:
            raise FixtureNotFoundError(
                "Fixture not found after update."
            )

        response = FixtureResponse.model_validate(
            fixture
        )

        await session.commit()

        return response

    except (
        FixtureValidationError,
        FixtureNotFoundError,
        FixtureConflictError,
    ) as error:
        await session.rollback()
        handle_fixture_error(error)

    except Exception:
        await session.rollback()
        raise



@router.get("/tournaments/{tournament_id}/bracket/review")
async def get_tournament_bracket_review(tournament_id: UUID, session: AsyncSession = Depends(get_db_session)):
    try:
        return await review_bracket(
            session,
            tournament_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc



@router.post("/bracket/dependencies/{dependency_id}/advance")
async def advance_bracket(dependency_id: UUID, session: AsyncSession = Depends(get_db_session)):
    try:
        async with session.begin():
            result = await advance_bracket_dependency(
                session=session,
                dependency_id=dependency_id,
            )

        return result

    except BracketAdvancementConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except BracketAdvancementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tournaments/{tournament_id}/export")
async def export_tournament_fixtures(tournament_id: UUID, session: AsyncSession = Depends(get_db_session)):
    fixtures = (
        await session.scalars(
            select(Fixture)
            .where(
                Fixture.tournament_id == tournament_id
            )
            .order_by(
                Fixture.fixture_number,
                Fixture.id,
            )
        )
    ).all()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Fixture Number",
        "Fixture ID",
        "Home Team ID",
        "Away Team ID",
        "Venue ID",
        "Scheduled At",
        "Status",
        "Match ID",
        "Version",
    ])

    for fixture in fixtures:
        writer.writerow([
            fixture.fixture_number,
            str(fixture.id),
            str(fixture.home_team_id or ""),
            str(fixture.away_team_id or ""),
            str(fixture.venue_id or ""),
            (
                fixture.scheduled_at.isoformat()
                if fixture.scheduled_at else ""
            ),
            fixture.status,
            str(fixture.match_id or ""),
            fixture.version,
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="fixtures.csv"'
            )
        },
    )
