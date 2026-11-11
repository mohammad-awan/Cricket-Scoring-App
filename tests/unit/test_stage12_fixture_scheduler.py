
from datetime import datetime, timedelta, timezone
import pytest
from app.domain.fixture_engine import Pairing, round_robin
from app.domain.fixture_scheduler import (
    Blackout,
    ScheduledFixture,
    TimeSlot,
    generate_schedule,
    validate_schedule,
)


UTC = timezone.utc


def dt(day, hour=10):
    return datetime(2026, 12, day, hour, tzinfo=UTC)


def test_schedule_two_teams():
    pairings = round_robin(["A", "B"])
    result = generate_schedule(
        pairings,
        slots=[
            TimeSlot("GROUND-1", dt(1)),
        ],
        duration=timedelta(hours=3),
        window_start=dt(1, 0),
        window_end=dt(2, 0),
    )
    assert result.feasible
    assert len(result.fixtures) == 1
    assert result.fixtures[0].venue_id == "GROUND-1"


def test_insufficient_slots_reports_failure():
    pairings = round_robin(["A", "B", "C", "D"])
    result = generate_schedule(
        pairings,
        slots=[
            TimeSlot("GROUND-1", dt(1)),
        ],
        duration=timedelta(hours=3),
        window_start=dt(1, 0),
        window_end=dt(2, 0),
    )
    assert not result.feasible
    assert len(result.fixtures) == 1
    assert len(result.conflicts) == 5


def test_venue_collision_is_detected():
    first = ScheduledFixture(
        1,
        Pairing(1, "A", "B"),
        "GROUND-1",
        dt(1, 10),
        dt(1, 13),
    )
    second = ScheduledFixture(
        2,
        Pairing(1, "C", "D"),
        "GROUND-1",
        dt(1, 11),
        dt(1, 14),
    )
    conflicts = validate_schedule([first, second])
    assert any(c.reason == "Venue collision." for c in conflicts)


def test_team_rest_conflict_is_detected():
    first = ScheduledFixture(
        1,
        Pairing(1, "A", "B"),
        "GROUND-1",
        dt(1, 10),
        dt(1, 13),
    )
    second = ScheduledFixture(
        2,
        Pairing(2, "A", "C"),
        "GROUND-2",
        dt(1, 14),
        dt(1, 17),
    )
    conflicts = validate_schedule([first, second], min_rest=timedelta(hours=3))
    assert any("insufficient rest" in c.reason for c in conflicts)


def test_venue_blackout_is_respected():
    pairings = [Pairing(1, "A", "B")]

    result = generate_schedule(
        pairings,
        slots=[
            TimeSlot("GROUND-1", dt(1, 10)),
            TimeSlot("GROUND-2", dt(1, 10)),
        ],
        duration=timedelta(hours=3),
        window_start=dt(1, 0),
        window_end=dt(2, 0),
        blackouts=[
            Blackout(
                dt(1, 9),
                dt(1, 15),
                venue_id="GROUND-1",
            ),
        ],
    )

    assert result.feasible
    assert result.fixtures[0].venue_id == "GROUND-2"


def test_existing_match_is_preserved():
    existing = ScheduledFixture(
        99,
        Pairing(1, "A", "B"),
        "GROUND-1",
        dt(1, 10),
        dt(1, 13),
    )

    result = generate_schedule(
        [Pairing(2, "C", "D")],
        slots=[
            TimeSlot("GROUND-1", dt(1, 10)),
            TimeSlot("GROUND-2", dt(1, 10)),
        ],
        duration=timedelta(hours=3),
        window_start=dt(1, 0),
        window_end=dt(2, 0),
        existing=[existing],
    )

    assert result.feasible
    assert result.fixtures[0].venue_id == "GROUND-2"
    assert existing.venue_id == "GROUND-1"


def test_schedule_is_deterministic():
    pairings = round_robin(["A", "B", "C", "D"])
    slots = [
        TimeSlot(
            "GROUND-1",
            dt(day, 10),
        )
        for day in range(1, 10)
    ]

    options = dict(
        slots=slots,
        duration=timedelta(hours=3),
        window_start=dt(1, 0),
        window_end=dt(10, 0),
        min_rest=timedelta(hours=12),
    )

    first = generate_schedule(pairings, **options)
    second = generate_schedule(pairings, **options)
    assert first == second
    assert first.feasible


def test_rejects_naive_datetime():
    with pytest.raises(ValueError):
        generate_schedule(
            [Pairing(1, "A", "B")],
            slots=[
                TimeSlot(
                    "GROUND-1",
                    datetime(2026, 12, 1, 10),
                )
            ],
            duration=timedelta(hours=3),
            window_start=dt(1, 0),
            window_end=dt(2, 0),
        )
