
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence
from app.domain.fixture_engine import Pairing, FixtureError


@dataclass(frozen=True)
class TimeSlot:
    venue_id: str
    start_at: datetime


@dataclass(frozen=True)
class Blackout:
    start_at: datetime
    end_at: datetime
    venue_id: str | None = None
    team_id: str | None = None


@dataclass(frozen=True)
class ScheduledFixture:
    fixture_number: int
    pairing: Pairing
    venue_id: str
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class ScheduleConflict:
    fixture_number: int
    reason: str


@dataclass(frozen=True)
class ScheduleResult:
    fixtures: tuple[ScheduledFixture, ...]
    conflicts: tuple[ScheduleConflict, ...]
    total_matches: int

    @property
    def feasible(self) -> bool:
        return (
            len(self.conflicts) == 0
            and len(self.fixtures) == self.total_matches
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FixtureError("All datetimes must include a timezone.")
    return value.astimezone(timezone.utc)


def overlaps(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    return start_a < end_b and start_b < end_a


def _has_rest_conflict(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
    rest: timedelta,
) -> bool:
    return start_a < end_b + rest and start_b < end_a + rest


def validate_interval(start: datetime, end: datetime) -> None:
    if _utc(start) >= _utc(end):
        raise FixtureError("Interval end must be after its start.")


def validate_schedule(
    fixtures: Sequence[ScheduledFixture],
    *,
    min_rest: timedelta = timedelta(0),
    blackouts: Sequence[Blackout] = (),
    existing: Sequence[ScheduledFixture] = (),
) -> list[ScheduleConflict]:
    """
    Check scheduled fixtures against hard constraints.

    The 'existing' parameter represents previously
    committed matches that must not be changed.
    """
    if min_rest < timedelta(0):
        raise FixtureError(
            "Minimum rest cannot be negative."
        )

    for blackout in blackouts:
        validate_interval(
            blackout.start_at,
            blackout.end_at,
        )
        if blackout.venue_id and blackout.team_id:
            raise FixtureError(
                "A blackout must target a venue or team, "
                "not both."
            )

    all_fixtures = list(existing) + list(fixtures)

    for fixture in all_fixtures:
        validate_interval(
            fixture.start_at,
            fixture.end_at,
        )
        if not fixture.venue_id.strip():
            raise FixtureError(
                "Venue ID cannot be empty."
            )
        if fixture.pairing.is_bye:
            raise FixtureError(
                "BYEs cannot be scheduled as matches."
            )
        if (
            fixture.pairing.home_team_id
            == fixture.pairing.away_team_id
        ):
            raise FixtureError(
                "A team cannot play itself."
            )

    conflicts: list[ScheduleConflict] = []
    existing_count = len(existing)

    for index in range(existing_count, len(all_fixtures)):
        current = all_fixtures[index]
        start = _utc(current.start_at)
        end = _utc(current.end_at)

        for blackout in blackouts:
            if not overlaps(
                start,
                end,
                _utc(blackout.start_at),
                _utc(blackout.end_at),
            ):
                continue

            applies = (
                blackout.venue_id is None
                and blackout.team_id is None
            ) or (
                blackout.venue_id == current.venue_id
            ) or (
                blackout.team_id in (
                    current.pairing.home_team_id,
                    current.pairing.away_team_id,
                )
                if blackout.team_id is not None
                else False
            )

            if applies:
                conflicts.append(
                    ScheduleConflict(
                        current.fixture_number,
                        "Blackout or unavailable period.",
                    )
                )

        # Compare against existing fixtures and earlier
        # proposed fixtures, avoiding duplicate reports.
        for other in all_fixtures[:index]:
            other_start = _utc(other.start_at)
            other_end = _utc(other.end_at)

            if (
                current.venue_id == other.venue_id
                and overlaps(
                    start, end,
                    other_start, other_end,
                )
            ):
                conflicts.append(
                    ScheduleConflict(
                        current.fixture_number,
                        "Venue collision.",
                    )
                )

            current_teams = {
                current.pairing.home_team_id,
                current.pairing.away_team_id,
            }
            other_teams = {
                other.pairing.home_team_id,
                other.pairing.away_team_id,
            }

            if current_teams & other_teams:
                if _has_rest_conflict(
                    start, end,
                    other_start, other_end,
                    min_rest,
                ):
                    conflicts.append(
                        ScheduleConflict(
                            current.fixture_number,
                            "Team overlap or insufficient rest.",
                        )
                    )

    return conflicts


def generate_schedule(
    pairings: Sequence[Pairing],
    *,
    slots: Sequence[TimeSlot],
    duration: timedelta,
    window_start: datetime,
    window_end: datetime,
    min_rest: timedelta = timedelta(0),
    playable_weekdays: set[int] | None = None,
    blackouts: Sequence[Blackout] = (),
    existing: Sequence[ScheduledFixture] = (),
) -> ScheduleResult:
    """
    Deterministic greedy scheduling.

    - Earlier slots are considered first.
    - Venues are sorted by ID for deterministic ties.
    - Existing matches remain unchanged.
    - No fabricated timeslots are created.
    - Unschedulable fixtures receive explicit conflicts.

    This is a feasibility-first heuristic, not a global
    soft-constraint optimization solver.
    """
    if duration <= timedelta(0):
        raise FixtureError(
            "Match duration must be positive."
        )

    if min_rest < timedelta(0):
        raise FixtureError(
            "Minimum rest cannot be negative."
        )

    validate_interval(
        window_start,
        window_end,
    )

    if playable_weekdays is not None:
        if not playable_weekdays or not (
            playable_weekdays <= set(range(7))
        ):
            raise FixtureError(
                "Weekdays must be integers from 0 to 6."
            )

    for slot in slots:
        _utc(slot.start_at)
        if not slot.venue_id.strip():
            raise FixtureError(
                "Venue ID cannot be empty."
            )
    # Validate fixed matches and blackout configuration.
    validate_schedule(
        (),
        min_rest=min_rest,
        blackouts=blackouts,
        existing=existing,
    )
    candidates = sorted(slots, key=lambda slot: (_utc(slot.start_at), slot.venue_id))

    window_start_utc = _utc(window_start)
    window_end_utc = _utc(window_end)
    scheduled: list[ScheduledFixture] = []
    conflicts: list[ScheduleConflict] = []

    games = [pairing for pairing in pairings if not pairing.is_bye]

    for fixture_number, pairing in enumerate(games, start=1):
        if pairing.home_team_id == pairing.away_team_id:
            raise FixtureError("A team cannot play itself.")

        placed = False

        for slot in candidates:
            start = _utc(slot.start_at)
            end = start + duration

            if start < window_start_utc or end > window_end_utc:
                continue

            # Weekday follows the local timezone
            # supplied for the timeslot.
            if (
                playable_weekdays is not None
                and slot.start_at.weekday()
                not in playable_weekdays
            ):
                continue

            candidate = ScheduledFixture(
                fixture_number=fixture_number,
                pairing=pairing,
                venue_id=slot.venue_id,
                start_at=slot.start_at,
                end_at=slot.start_at + duration,
            )

            violations = validate_schedule(
                [candidate],
                min_rest=min_rest,
                blackouts=blackouts,
                existing=[*existing, *scheduled],
            )

            if violations:
                continue

            scheduled.append(candidate)
            placed = True
            break

        if not placed:
            conflicts.append(
                ScheduleConflict(
                    fixture_number=fixture_number,
                    reason=(
                        "No feasible venue/timeslot within "
                        "the competition window and hard "
                        "scheduling constraints."
                    ),
                )
            )

    return ScheduleResult(
        fixtures=tuple(scheduled),
        conflicts=tuple(conflicts),
        total_matches=len(games),
    )
