"""Pure fixture previews and feasibility reports; no ORM or database writes."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
import random
from statistics import pstdev
from zoneinfo import ZoneInfo

from app.domain.fixture_engine import (
    FixtureError, Pairing, knockout_bracket, random_round_robin, round_robin, validate_manual,
)
from app.domain.fixture_scheduler import (
    Blackout, ScheduledFixture, TimeSlot, generate_schedule, validate_schedule,
)
from app.schemas.fixture_planning import FixturePlanRequest

ALGORITHM_VERSION = "circle-greedy-2.0"


def issue(number, code, message, severity="error"):
    return {"fixture_number": number, "code": code, "message": message, "severity": severity}


def scheduled(row):
    """Unknown bracket slots use distinct dependency identities, never fake teams."""
    return ScheduledFixture(
        row["fixture_number"],
        Pairing(row["round_number"], row.get("home_team_id") or row.get("home_source") or f'home:{row["fixture_number"]}',
                row.get("away_team_id") or row.get("away_source") or f'away:{row["fixture_number"]}'),
        str(row["venue_id"]), row["scheduled_at"], row["ends_at"],
    )


def blackouts(config):
    return [Blackout(item.start_at, item.end_at,
                     str(item.venue_id) if item.venue_id else None,
                     str(item.team_id) if item.team_id else None) for item in config.blackouts]


def draw_groups(config, teams):
    if config.groups:
        groups = {name.strip(): [str(team) for team in members] for name, members in config.groups.items()}
        flat = [team for members in groups.values() for team in members]
        if len(flat) != len(set(flat)) or set(flat) != set(teams):
            raise FixtureError("Each selected team must appear in exactly one group.")
    else:
        if len(teams) < config.group_count * 2:
            raise FixtureError("Each group needs at least two teams.")
        groups = {chr(65 + index): [] for index in range(config.group_count)}
        rng = random.Random(config.seed)
        pots = [[str(team) for team in pot] for pot in config.seed_pots] or [teams[:]]
        flat = [team for pot in pots for team in pot]
        if len(flat) != len(set(flat)) or set(flat) != set(teams):
            raise FixtureError("Seed pots must contain every selected team exactly once.")
        cursor = 0
        for pot in pots:
            if config.method == "random":
                rng.shuffle(pot)
            for team in pot:
                groups[list(groups)[cursor % len(groups)]].append(team)
                cursor += 1
    if any(not name or len(members) < 2 for name, members in groups.items()):
        raise FixtureError("Groups need names and at least two teams.")
    return groups


def make_plan(config: FixturePlanRequest, approved: list[str], *, existing=(), extra_blackouts=()):
    teams = [str(team) for team in config.team_ids] or list(approved)
    if len(teams) < 2 or not set(teams) <= set(approved):
        raise FixtureError("Select at least two approved, active, non-reserve teams.")
    rows, byes, groups = [], [], {}
    format_name = "knockout" if config.method == "knockout" else config.format

    def add_pairings(pairings, group=None):
        for pair in pairings:
            if pair.is_bye:
                byes.append({"round_number": pair.round_number, "team_id": pair.home_team_id or pair.away_team_id, "group": group, "leg": pair.leg})
                continue
            rows.append({"fixture_number": len(rows) + 1, "round_number": pair.round_number,
                         "home_team_id": pair.home_team_id, "away_team_id": pair.away_team_id,
                         "home_source": None, "away_source": None, "leg": pair.leg,
                         "group": group, "stage": "group" if group else "league",
                         "venue_id": None, "scheduled_at": None, "ends_at": None, "notes": None,
                         "explanation": "Manual organizer pairing." if config.method == "manual" else
                         f"Circle-method opponent pairing; leg {pair.leg}, round {pair.round_number}."})

    def add_knockout(entries, round_offset=0):
        first_number = len(rows)
        slots = knockout_bracket(entries, seed=config.seed if config.method == "random" else None)
        for slot in slots:
            sources = {}
            for side in ("home", "away"):
                source = getattr(slot, f"{side}_source")
                team = getattr(slot, f"{side}_team_id")
                if source:
                    source = f"winner:{first_number + int(source.split(':')[1])}"
                elif team and team.startswith("group:"):
                    source, team = team, None
                sources[f"{side}_team_id"] = team
                sources[f"{side}_source"] = source
            rows.append({"fixture_number": first_number + slot.match_number,
                         "round_number": round_offset + slot.round_number,
                         **sources, "leg": 1, "group": None, "stage": "knockout",
                         "venue_id": None, "scheduled_at": None, "ends_at": None, "notes": None,
                         "explanation": "Single-elimination slot. Only finalized winners can resolve its dependencies."})
        # The engine assigns preliminary byes to the front of its draw order.
        ordered = entries[:]
        if config.method == "random":
            random.Random(config.seed).shuffle(ordered)
        for team in ordered[:(1 << (len(entries) - 1).bit_length()) - len(entries)]:
            byes.append({"round_number": round_offset + 1, "team_id": None if team.startswith("group:") else team,
                         "source": team if team.startswith("group:") else None, "group": None, "leg": 1})

    if config.method == "manual":
        for entry in config.pairings:
            data = entry.model_dump()
            add_pairings([Pairing(entry.round_number, str(entry.home_team_id), str(entry.away_team_id), entry.leg)])
            rows[-1].update({key: str(data[key]) if key == "venue_id" and data[key] else data[key]
                             for key in ("venue_id", "scheduled_at", "ends_at", "notes")})
    elif format_name == "knockout":
        add_knockout(teams)
    else:
        groups = draw_groups(config, teams) if format_name in {"groups", "hybrid"} else {}
        for group, members in (groups or {None: teams}).items():
            pairings = (random_round_robin(members, seed=config.seed, legs=config.legs)
                        if config.method == "random" else round_robin(members, legs=config.legs))
            add_pairings(pairings, group)
        if format_name == "hybrid":
            if any(len(members) < config.advance_per_group for members in groups.values()):
                raise FixtureError("Advancing places cannot exceed a group's team count.")
            names = list(groups)
            ranked = [f"group:{name}:{rank}" for rank in range(1, config.advance_per_group + 1) for name in names]
            entrants = []
            while ranked:
                first = ranked.pop(0)
                entrants.append(first)
                if ranked:
                    different = [index for index, item in enumerate(ranked) if item.split(":")[1] != first.split(":")[1]]
                    entrants.append(ranked.pop(different[-1] if different else -1))
            if len(entrants) < 2:
                raise FixtureError("At least two group qualifiers are required.")
            offset = max(row["round_number"] for row in rows)
            add_knockout(entrants, offset)
    if len(rows) > 5000:
        raise FixtureError("This plan exceeds the 5,000-fixture preview limit. Split it into competitions.")

    allocation_issues = allocate_rows(config, rows, existing=existing, extra_blackouts=extra_blackouts) if config.auto_schedule and config.method != "manual" else []
    result = analyze(rows, config, teams, groups=groups, existing=existing, extra_blackouts=extra_blackouts)
    result["violations"] = allocation_issues + result["violations"]
    result["valid"] = not any(item["severity"] == "error" for item in result["violations"])
    result.update(fixtures=rows, byes=byes, groups=groups, algorithm_version=ALGORITHM_VERSION,
                  configuration=config.model_dump(mode="json"), seed=config.seed)
    return result


def allocate_rows(config, rows, *, existing=(), extra_blackouts=()):
    allocation_issues = []
    if rows:
        if not config.start_date or not config.end_date or not config.venue_ids or not config.times:
            allocation_issues.append(issue(None, "schedule_inputs", "Select dates, venues and at least one start time to allocate fixtures."))
        else:
            zone = ZoneInfo(config.timezone)
            start = datetime.combine(config.start_date, time.min, zone)
            end = datetime.combine(config.end_date + timedelta(days=1), time.min, zone)
            slots = []
            day = config.start_date
            while day <= config.end_date:
                if day.weekday() in config.weekdays:
                    for at in sorted(set(config.times)):
                        candidate = datetime.combine(day, at, zone)
                        # A spring DST jump can make a wall-clock time nonexistent.
                        if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                            continue
                        slots.extend(TimeSlot(str(venue), candidate) for venue in config.venue_ids)
                day += timedelta(days=1)
            fixed = list(existing)
            previous_end = None
            for round_number in sorted({row["round_number"] for row in rows}):
                batch = [row for row in rows if row["round_number"] == round_number]
                candidates = [slot for slot in slots if not previous_end or slot.start_at >= previous_end.astimezone(timezone.utc) + timedelta(minutes=config.minimum_rest_minutes)]
                if config.final_date and all(row["stage"] == "knockout" for row in batch) and len(batch) == 1:
                    candidates = [slot for slot in candidates if slot.start_at.date() == config.final_date]
                result = generate_schedule([scheduled({**row, "venue_id": "pending"}).pairing for row in batch],
                    slots=candidates, duration=timedelta(minutes=config.duration_minutes),
                    window_start=start, window_end=end, min_rest=timedelta(minutes=config.minimum_rest_minutes),
                    blackouts=[*blackouts(config), *extra_blackouts], existing=fixed)
                for placed in result.fixtures:
                    row = batch[placed.fixture_number - 1]
                    row.update(venue_id=placed.venue_id, scheduled_at=placed.start_at, ends_at=placed.end_at)
                    row["explanation"] += " Earliest feasible supplied slot; prior rounds, rest, blackouts and existing matches are protected."
                    fixed.append(scheduled(row))
                allocation_issues.extend(issue(batch[item.fixture_number - 1]["fixture_number"], "capacity", item.reason) for item in result.conflicts)
                if result.fixtures:
                    previous_end = max(item.end_at for item in result.fixtures)
                if result.conflicts:
                    # A dependent round cannot precede an unscheduled prerequisite.
                    break
    return allocation_issues


def analyze(rows, config, teams, *, groups=None, existing=(), extra_blackouts=()):
    violations, placed = [], []
    by_number = {row["fixture_number"]: row for row in rows}
    venues = set(map(str, config.venue_ids))
    counts = Counter({team: 0 for team in teams})
    usage, gaps, appearances = Counter(), [], defaultdict(list)
    for row in rows:
        number = row["fixture_number"]
        if row.get("status") == "cancelled":
            continue
        home, away = row.get("home_team_id"), row.get("away_team_id")
        if home and home == away:
            violations.append(issue(number, "self_opponent", "A team cannot play itself."))
        for side in ("home", "away"):
            team, source = row.get(f"{side}_team_id"), row.get(f"{side}_source")
            if team:
                counts[team] += 1
                if team not in teams:
                    violations.append(issue(number, "team_unavailable", "An assigned team is no longer approved or was not selected."))
            elif not source:
                violations.append(issue(number, "missing_team", "Both opponents or valid bracket dependencies are required."))
            elif source.startswith("winner:"):
                predecessor = by_number.get(int(source.split(":")[1]))
                if not predecessor or predecessor["round_number"] >= row["round_number"]:
                    violations.append(issue(number, "dependency", "A bracket dependency must reference an earlier round."))
                elif row.get("scheduled_at") and (not predecessor.get("ends_at") or row["scheduled_at"] < predecessor["ends_at"].astimezone(timezone.utc) + timedelta(minutes=config.minimum_rest_minutes)):
                    violations.append(issue(number, "dependency_time", "A dependent match must follow its source and the minimum rest interval."))
            elif source.startswith("group:"):
                group_name = source.split(":")[1]
                prerequisites = [entry for entry in rows if entry.get("group") == group_name]
                if row.get("scheduled_at") and any(not entry.get("ends_at") or row["scheduled_at"] < entry["ends_at"].astimezone(timezone.utc) + timedelta(minutes=config.minimum_rest_minutes) for entry in prerequisites):
                    violations.append(issue(number, "group_dependency_time", "A qualifier match must follow all group games and the minimum rest interval."))
        start, end, venue = row.get("scheduled_at"), row.get("ends_at"), row.get("venue_id")
        if not start or not end or not venue:
            violations.append(issue(number, "unscheduled", "Choose a venue, start and end time before publishing."))
            continue
        if end <= start:
            violations.append(issue(number, "interval", "End time must follow start time."))
            continue
        if venue not in venues:
            violations.append(issue(number, "venue", "Select a permitted venue from this plan."))
        local_start, local_end = start.astimezone(ZoneInfo(config.timezone)), end.astimezone(ZoneInfo(config.timezone))
        if (config.start_date and local_start.date() < config.start_date) or (config.end_date and local_end > datetime.combine(config.end_date + timedelta(days=1), time.min, ZoneInfo(config.timezone))):
            violations.append(issue(number, "window", "Fixture lies outside the competition window."))
        if local_start.weekday() not in config.weekdays:
            violations.append(issue(number, "weekday", "Fixture falls on an unavailable weekday."))
        placed.append(scheduled(row))
        usage[venue] += 1
        for team in (home, away):
            if team:
                appearances[team].append((start, end))
    try:
        violations.extend(issue(item.fixture_number, "collision", item.reason) for item in
                          validate_schedule(placed, min_rest=timedelta(minutes=config.minimum_rest_minutes),
                                            blackouts=[*blackouts(config), *extra_blackouts], existing=existing))
    except FixtureError as error:
        violations.append(issue(None, "schedule", str(error)))
    # Validate completeness and per-round appearances after manual overrides too.
    for group, members in (groups or {None: teams}).items():
        league = [row for row in rows if row.get("stage") != "knockout" and row.get("group") == group]
        if (not league and config.format == "knockout") or config.method == "knockout":
            continue
        if league or config.method == "manual":
            try:
                validate_manual([Pairing(row["round_number"], row.get("home_team_id"), row.get("away_team_id"), row.get("leg", 1)) for row in league], allowed_team_ids=members, legs=config.legs)
            except FixtureError as error:
                violations.append(issue(None, "pairing", str(error)))
    for team, intervals in appearances.items():
        ordered = sorted(intervals)
        gaps.extend((later[0].astimezone(timezone.utc) - earlier[1].astimezone(timezone.utc)).total_seconds() / 60 for earlier, later in zip(ordered, ordered[1:]))
    if not rows:
        violations.append(issue(None, "empty", "Add fixtures to this draft."))
    return {"valid": not violations, "violations": violations,
            "summary": {"matches": len(rows), "scheduled": len(placed),
                        "rounds": len({row["round_number"] for row in rows}),
                        "team_counts": dict(counts), "venue_utilization": dict(usage),
                        "minimum_rest_minutes": round(min(gaps), 1) if gaps else None,
                        "rest_spread_minutes": round(pstdev(gaps), 1) if gaps else 0,
                        "penalty_score": round((pstdev(gaps) if gaps else 0) + (pstdev([usage[venue] for venue in venues]) if venues else 0), 2)},
            "limitations": ["Allocation uses a deterministic feasibility-first heuristic; the score describes rest and venue imbalance.",
                            "Group qualifiers stay blocked until official Stage 13 rankings are available. Historical win probabilities are not used."]}
