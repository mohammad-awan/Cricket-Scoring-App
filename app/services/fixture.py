from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.fixture_engine import (
    FixtureError,
    Pairing,
    knockout_bracket,
    random_round_robin,
    round_robin,
    validate_manual,
)
from app.models.entities.fixtures import (
    Fixture,
    FixtureBracketDependency,
    FixtureChangeAudit,
    FixtureGenerationRun,
    FixtureRound,
)
import app.models  # noqa: F401
from app.db.base import Base


# ==================================================
# EXCEPTIONS
# ==================================================

class FixtureServiceError(Exception):
    """Base error for fixture operations."""


class FixtureValidationError(FixtureServiceError):
    """The supplied fixture plan is invalid."""


class FixtureNotFoundError(FixtureServiceError):
    """The requested tournament, run, or fixture was not found."""


class FixtureConflictError(FixtureServiceError):
    """A fixture is locked, published, or has an outdated version."""


# ==================================================
# RESULT DATA
# ==================================================

@dataclass(frozen=True)
class FixtureGenerationResult:
    generation_run_id: UUID
    tournament_id: UUID
    fixture_count: int
    round_count: int


# ==================================================
# HELPERS
# ==================================================

def _uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None

    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise FixtureValidationError(
            f"Invalid team ID: {value!r}"
        ) from exc


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


# ==================================================
# FIXTURE SERVICE
# ==================================================

class FixtureService:
    """
    Stage 12 fixture persistence service.

    Uses the existing SQLAlchemy AsyncSession.

    The caller controls commit and rollback.

    This service does not create scoring Match rows.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ----------------------------------------------
    # LOAD APPROVED TOURNAMENT TEAMS
    # ----------------------------------------------

    async def _approved_teams(
        self,
        tournament_id: UUID,
    ) -> list[str]:

        tournaments = Base.metadata.tables["tournaments"]
        memberships = Base.metadata.tables["tournament_teams"]

        exists = await self.session.scalar(
            select(tournaments.c.id).where(
                tournaments.c.id == tournament_id
            )
        )

        if exists is None:
            raise FixtureNotFoundError(
                "Tournament does not exist."
            )

        conditions = [
            memberships.c.tournament_id == tournament_id,
            memberships.c.registration_status == "approved",
        ]

        # Support projects where reserve membership
        # is represented by an optional column.
        if "is_reserve" in memberships.c:
            conditions.append(
                memberships.c.is_reserve.is_(False)
            )

        query = select(memberships.c.team_id).where(
            *conditions
        )

        if "seed" in memberships.c:
            query = query.order_by(
                memberships.c.seed.asc().nulls_last(),
                memberships.c.team_id,
            )
        else:
            query = query.order_by(
                memberships.c.team_id
            )

        result = await self.session.execute(query)

        teams = [
            str(row[0])
            for row in result.all()
        ]

        if len(teams) < 2:
            raise FixtureValidationError(
                "At least two approved tournament teams "
                "are required."
            )

        return teams

    # ----------------------------------------------
    # GENERATE AND SAVE FIXTURES
    # ----------------------------------------------

    async def generate_fixtures(
        self,
        *,
        tournament_id: UUID,
        method: str,
        configuration: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> FixtureGenerationResult:

        supported_methods = {
            "manual",
            "random",
            "round_robin",
            "knockout",
        }

        if method not in supported_methods:
            raise FixtureValidationError(
                "Unsupported fixture generation method."
            )

        config = dict(configuration or {})

        teams = await self._approved_teams(
            tournament_id
        )

        try:

            # KNOCKOUT
            if method == "knockout":

                if config:
                    raise FixtureValidationError(
                        "Knockout configuration options "
                        "are not supported yet."
                    )

                slots = knockout_bracket(
                    teams,
                    seed=seed,
                )

                plan = [
                    (
                        slot.round_number,
                        slot.home_team_id,
                        slot.away_team_id,
                        slot,
                    )
                    for slot in slots
                ]

            # ROUND ROBIN / RANDOM / MANUAL
            else:

                allowed_keys = (
                    {"legs", "pairings"}
                    if method == "manual"
                    else {"legs"}
                )

                if set(config) - allowed_keys:
                    raise FixtureValidationError(
                        "Unsupported configuration keys."
                    )

                legs = config.get("legs", 1)

                if (
                    type(legs) is not int
                    or legs not in (1, 2)
                ):
                    raise FixtureValidationError(
                        "legs must be 1 or 2."
                    )

                if method == "random":

                    if seed is None:
                        raise FixtureValidationError(
                            "Random fixture generation "
                            "requires a seed."
                        )

                    pairings = random_round_robin(
                        teams,
                        seed=seed,
                        legs=legs,
                    )

                elif method == "round_robin":

                    pairings = round_robin(
                        teams,
                        legs=legs,
                    )

                else:

                    raw = config.get("pairings")

                    if not isinstance(raw, list):
                        raise FixtureValidationError(
                            "Manual generation requires "
                            "a pairings list."
                        )

                    pairings = [
                        Pairing(**item)
                        for item in raw
                    ]

                    validate_manual(
                        pairings,
                        allowed_team_ids=teams,
                        legs=legs,
                    )

                # BYEs are not playable matches.
                plan = [
                    (
                        pairing.round_number,
                        pairing.home_team_id,
                        pairing.away_team_id,
                        None,
                    )
                    for pairing in pairings
                    if not pairing.is_bye
                ]

        except (
            FixtureError,
            TypeError,
            KeyError,
            ValueError,
        ) as exc:
            raise FixtureValidationError(
                str(exc)
            ) from exc

        if not plan:
            raise FixtureValidationError(
                "Fixture generation produced no matches."
            )

        # ------------------------------------------
        # CREATE GENERATION RUN
        # ------------------------------------------

        run_id = uuid4()

        run = FixtureGenerationRun(
            id=run_id,
            tournament_id=tournament_id,
            method=method,
            seed=seed,
            configuration=_json_safe(config),
            status="draft",
        )

        self.session.add(run)

        # ------------------------------------------
        # CREATE ROUNDS
        # ------------------------------------------

        round_ids: dict[int, UUID] = {}

        round_numbers = sorted({
            item[0]
            for item in plan
        })

        for round_number in round_numbers:

            round_id = uuid4()

            round_ids[round_number] = round_id

            fixture_round = FixtureRound(
                id=round_id,
                tournament_id=tournament_id,
                generation_run_id=run_id,
                round_number=round_number,
                stage=(
                    "knockout"
                    if method == "knockout"
                    else "league"
                ),
            )

            self.session.add(fixture_round)

        # ------------------------------------------
        # CREATE FIXTURES
        # ------------------------------------------

        slot_to_fixture: dict[int, UUID] = {}

        dependencies: list[
            tuple[UUID, str, str]
        ] = []

        for number, (
            round_number,
            home,
            away,
            slot,
        ) in enumerate(plan, start=1):

            fixture_id = uuid4()

            fixture = Fixture(
                id=fixture_id,
                tournament_id=tournament_id,
                generation_run_id=run_id,
                round_id=round_ids[round_number],
                fixture_number=number,
                home_team_id=_uuid(home),
                away_team_id=_uuid(away),
                status="draft",
                version=1,
                is_locked=False,
            )

            self.session.add(fixture)

            if slot is not None:

                slot_to_fixture[
                    slot.match_number
                ] = fixture_id

                for side in ("home", "away"):

                    source = getattr(
                        slot,
                        f"{side}_source",
                    )

                    if source:
                        dependencies.append(
                            (
                                fixture_id,
                                side,
                                source,
                            )
                        )

        # ------------------------------------------
        # CREATE KNOCKOUT DEPENDENCIES
        # ------------------------------------------

        for (
            target_id,
            side,
            source,
        ) in dependencies:

            prefix, separator, source_number = (
                source.partition(":")
            )

            if (
                separator != ":"
                or prefix != "winner"
            ):
                raise FixtureValidationError(
                    f"Unsupported bracket source: {source}"
                )

            try:
                source_id = slot_to_fixture[
                    int(source_number)
                ]

            except (ValueError, KeyError) as exc:
                raise FixtureValidationError(
                    f"Unknown bracket source: {source}"
                ) from exc

            dependency = FixtureBracketDependency(
                id=uuid4(),
                fixture_id=target_id,
                source_fixture_id=source_id,
                target_side=side,
                advancement="winner",
            )

            self.session.add(dependency)

        # Flush, but do not commit.
        await self.session.flush()

        return FixtureGenerationResult(
            generation_run_id=run_id,
            tournament_id=tournament_id,
            fixture_count=len(plan),
            round_count=len(round_ids),
        )

    # ----------------------------------------------
    # PUBLISH FIXTURE GENERATION
    # ----------------------------------------------

    async def publish_generation(
        self,
        *,
        generation_run_id: UUID,
        expected_fixture_count: int,
    ) -> int:

        if expected_fixture_count < 1:
            raise FixtureValidationError(
                "Expected fixture count must be positive."
            )

        run = await self.session.scalar(
            select(FixtureGenerationRun)
            .where(
                FixtureGenerationRun.id
                == generation_run_id
            )
            .with_for_update()
        )

        if run is None:
            raise FixtureNotFoundError(
                "Fixture generation run not found."
            )

        if run.status != "draft":
            raise FixtureConflictError(
                "Only draft generation runs "
                "can be published."
            )

        result = await self.session.scalars(
            select(Fixture)
            .where(
                Fixture.generation_run_id
                == generation_run_id
            )
            .order_by(Fixture.fixture_number)
            .with_for_update()
        )

        fixtures = list(result.all())

        if len(fixtures) != expected_fixture_count:
            raise FixtureConflictError(
                "Fixture count changed; "
                "publication cancelled."
            )

        if any(
            fixture.status != "draft"
            or fixture.is_locked
            for fixture in fixtures
        ):
            raise FixtureConflictError("All fixtures must be unlocked drafts.")

        now = datetime.now(timezone.utc)

        for fixture in fixtures:
            fixture.status = "published"
            fixture.published_at = now
            fixture.version += 1

        run.status = "published"
        run.published_at = now

        await self.session.flush()

        return len(fixtures)

    # ----------------------------------------------
    # UPDATE FIXTURE
    # ----------------------------------------------

    async def update_fixture(
        self,
        *,
        fixture_id: UUID,
        expected_version: int,
        changes: dict[str, Any],
    ) -> None:

        if expected_version < 1:
            raise FixtureValidationError("Version must be positive.")

        allowed = {
            "home_team_id",
            "away_team_id",
            "venue_id",
            "scheduled_at",
            "ends_at",
            "notes",
        }

        if not changes or set(changes) - allowed:
            raise FixtureValidationError("No changes or unsupported fixture fields.")

        fixture = await self.session.scalar(
            select(Fixture)
            .where(Fixture.id == fixture_id)
            .with_for_update()
        )

        if fixture is None:
            raise FixtureNotFoundError("Fixture not found.")

        if (
            fixture.is_locked
            or fixture.match_id is not None
            or fixture.status != "draft"
        ):
            raise FixtureConflictError(
                "Only unlocked, unlinked draft "
                "fixtures can be edited."
            )

        if fixture.version != expected_version:
            raise FixtureConflictError(
                "Fixture version conflict."
            )

        values = {
            key: getattr(fixture, key)
            for key in allowed
        }

        values.update(changes)

        if (
            values["home_team_id"] is not None
            and values["home_team_id"]
            == values["away_team_id"]
        ):
            raise FixtureValidationError(
                "Home and away teams must differ."
            )

        start = values["scheduled_at"]
        end = values["ends_at"]

        if start is not None and end is not None:

            try:
                if end <= start:
                    raise FixtureValidationError(
                        "End time must follow start time."
                    )

            except TypeError as exc:
                raise FixtureValidationError(
                    "Incompatible scheduling datetimes."
                ) from exc

        # Validate any changed team assignments.
        if any(
            key in changes
            for key in (
                "home_team_id",
                "away_team_id",
            )
        ):

            approved = set(
                await self._approved_teams(
                    fixture.tournament_id
                )
            )

            for key in (
                "home_team_id",
                "away_team_id",
            ):

                team_id = values[key]

                if (
                    team_id is not None
                    and str(team_id) not in approved
                ):
                    raise FixtureValidationError(
                        "Fixture team is not an "
                        "approved tournament team."
                    )

        # Record previous values.
        old_values = {
            key: _json_safe(
                getattr(fixture, key)
            )
            for key in changes
        }

        # Apply updates.
        for key, value in changes.items():
            setattr(fixture, key, value)

        fixture.version += 1

        # Record audit history.
        audit = FixtureChangeAudit(
            id=uuid4(),
            fixture_id=fixture_id,
            action="updated",
            old_values=old_values,
            new_values={
                key: _json_safe(value)
                for key, value in changes.items()
            },
        )

        self.session.add(audit)
        await self.session.flush()
