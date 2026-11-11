"""Transactional Stage 12 planning, publication and bracket progression.

The existing generation/round/fixture tables remain the source of truth.
Typed planning inputs and source explanations are versioned in the run's JSON
configuration; fixture edits and result changes use the existing audit table.
"""
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.domain.fixture_engine import FixtureError
from app.domain.fixture_planning import ALGORITHM_VERSION, allocate_rows, analyze, issue, make_plan, scheduled
from app.domain.fixture_scheduler import Blackout
from app.models import Match, MatchStatus, MatchType
from app.models.entities.fixtures import Fixture, FixtureBracketDependency, FixtureChangeAudit, FixtureGenerationRun, FixtureRound
from app.repositories.fixtures import FixtureRepository
from app.schemas.fixture_planning import FixturePlanRequest
from app.schemas.fixtures import FixtureResponse
from app.services.fixture import FixtureConflictError, FixtureNotFoundError, FixtureValidationError, _json_safe
from app.services.match_setup.tournament_snapshot import apply_tournament_fixture_rules


class FixturePlanningService:
    def __init__(self, session):
        self.session = session
        self.repo = FixtureRepository(session)

    async def context(self, tournament_id, config, exclude_run=None, lock=False):
        tournament = await self.repo.tournament(tournament_id, lock)
        if tournament is None:
            raise FixtureNotFoundError("Tournament not found.")
        if lock and tournament.status in {"completed", "cancelled", "archived"}:
            raise FixtureConflictError("This tournament no longer accepts fixture changes.")
        teams = [str(member.team_id) for member in await self.repo.teams(tournament_id)]
        permitted = {str(venue.id) for venue in await self.repo.venues(tournament_id)}
        if not set(map(str, config.venue_ids)) <= permitted:
            raise FixtureValidationError("Choose active venues assigned to this tournament.")
        if config.auto_schedule and (not config.start_date or not config.end_date):
            raise FixtureValidationError("A scheduling date range is required.")
        if (tournament.start_date and config.start_date and config.start_date < tournament.start_date) or (tournament.end_date and config.end_date and config.end_date > tournament.end_date):
            raise FixtureValidationError("The date range must lie within the tournament dates.")
        if config.timezone != tournament.timezone:
            raise FixtureValidationError("Use the tournament timezone when planning fixtures.")
        availability = await self.repo.availability(config.venue_ids)
        blackouts = [Blackout(row.start_at, row.end_at, str(row.venue_id)) for row in availability if not row.is_available]
        if config.start_date and config.end_date:
            zone = ZoneInfo(config.timezone)
            window_start = datetime.combine(config.start_date, time.min, zone)
            window_end = datetime.combine(config.end_date + timedelta(days=1), time.min, zone)
            for venue_id in config.venue_ids:
                allowed = sorted((row.start_at, row.end_at) for row in availability
                                 if row.is_available and row.tournament_id == tournament_id and row.venue_id == venue_id)
                cursor = window_start
                for start, end in allowed:
                    if start > cursor and cursor < window_end:
                        blackouts.append(Blackout(cursor, min(start, window_end), str(venue_id)))
                    cursor = max(cursor, end)
                if allowed and cursor < window_end:
                    blackouts.append(Blackout(cursor, window_end, str(venue_id)))
        for constraint in await self.repo.constraints(tournament_id):
            if constraint.name == "minimum_rest":
                if config.minimum_rest_minutes < constraint.configuration.get("minutes", 0):
                    raise FixtureValidationError("The requested rest interval is below the tournament minimum.")
            elif constraint.name == "blackouts":
                from app.schemas.fixture_planning import BlackoutInput
                try:
                    for item in constraint.configuration.get("periods", []):
                        entry = BlackoutInput.model_validate(item)
                        blackouts.append(Blackout(entry.start_at, entry.end_at, str(entry.venue_id) if entry.venue_id else None, str(entry.team_id) if entry.team_id else None))
                except ValueError as error:
                    raise FixtureValidationError("A stored blackout constraint is invalid.") from error
            else:
                raise FixtureValidationError(f"Active scheduling constraint '{constraint.name}' needs a supported definition before generation.")
        external = await self.repo.external(config, exclude_run)
        return tournament, teams, availability, blackouts, external

    async def preview(self, tournament_id, config):
        _, teams, availability, blackouts, external = await self.context(tournament_id, config)
        try:
            result = make_plan(config, teams, existing=external, extra_blackouts=blackouts)
        except FixtureError as error:
            raise FixtureValidationError(str(error)) from error
        self.check_availability(result, availability, tournament_id)
        return result

    @staticmethod
    def check_availability(result, availability, tournament_id):
        for row in result["fixtures"]:
            intervals = [entry for entry in availability if entry.is_available and
                         entry.tournament_id == tournament_id and str(entry.venue_id) == row.get("venue_id")]
            if intervals and row.get("scheduled_at") and row.get("ends_at") and not any(
                entry.start_at <= row["scheduled_at"] and row["ends_at"] <= entry.end_at for entry in intervals):
                result["violations"].append(issue(row["fixture_number"], "availability", "Fixture lies outside this venue's available intervals."))
        result["valid"] = not any(item["severity"] == "error" for item in result["violations"])

    async def save(self, tournament_id, config):
        await self.repo.scheduling_lock()
        # Serializing on the tournament makes request replay safe across workers.
        await self.context(tournament_id, config, lock=True)
        encoded = config.model_dump(mode="json", exclude={"request_id"})
        fingerprint = sha256(json.dumps(encoded, sort_keys=True).encode()).hexdigest()
        for run in await self.repo.runs(tournament_id):
            stored = run.configuration or {}
            if stored.get("request_id") == str(config.request_id):
                if stored.get("fingerprint") != fingerprint:
                    raise FixtureConflictError("This request ID was already used for different inputs.")
                return {"generation_run_id": run.id, "replayed": True}
        result = await self.preview(tournament_id, config)
        run = FixtureGenerationRun(id=uuid4(), tournament_id=tournament_id, method=config.method,
            seed=config.seed, algorithm_version=ALGORITHM_VERSION, status="draft",
            configuration={"planning": encoded, "request_id": str(config.request_id), "fingerprint": fingerprint,
                           "snapshot": _json_safe(result)})
        self.session.add(run)
        await self.session.flush()
        rounds = {}
        for number in sorted({row["round_number"] for row in result["fixtures"]}):
            rounds[number] = FixtureRound(id=uuid4(), tournament_id=tournament_id, generation_run_id=run.id,
                round_number=number, stage="knockout" if all(row["stage"] == "knockout" for row in result["fixtures"] if row["round_number"] == number) else "league")
            self.session.add(rounds[number])
        await self.session.flush()
        fixtures = {}
        for row in result["fixtures"]:
            fixture = Fixture(id=uuid4(), tournament_id=tournament_id, generation_run_id=run.id,
                round_id=rounds[row["round_number"]].id, fixture_number=row["fixture_number"], status="draft", version=1, is_locked=False,
                **{key: UUID(row[key]) if row[key] and key.endswith("_id") else row[key]
                   for key in ("home_team_id", "away_team_id", "venue_id", "scheduled_at", "ends_at", "notes")})
            self.session.add(fixture)
            fixtures[fixture.fixture_number] = fixture
        await self.session.flush()
        for row in result["fixtures"]:
            for side in ("home", "away"):
                source = row[f"{side}_source"]
                if source and source.startswith("winner:"):
                    self.session.add(FixtureBracketDependency(id=uuid4(), fixture_id=fixtures[row["fixture_number"]].id,
                        source_fixture_id=fixtures[int(source.split(":")[1])].id, target_side=side, advancement="winner"))
            self.log(fixtures[row["fixture_number"]], "draft_created", {}, {"algorithm": ALGORITHM_VERSION}, "Organizer saved fixture preview")
        await self.session.flush()
        return {"generation_run_id": run.id, "replayed": False}

    def log(self, fixture, action, before, after, reason):
        self.session.add(FixtureChangeAudit(id=uuid4(), fixture_id=fixture.id, action=action,
            old_values=_json_safe(before), new_values=_json_safe(after), reason=reason))

    async def load(self, run_id, lock=False):
        run = await self.repo.run(run_id, lock)
        if run is None:
            raise FixtureNotFoundError("Generation run not found.")
        fixtures = await self.repo.fixtures(run_id, lock)
        rounds = {row.id: row.round_number for row in await self.repo.rounds(run_id)}
        metadata = {row["fixture_number"]: row for row in (run.configuration or {}).get("snapshot", {}).get("fixtures", [])}
        rows = []
        for fixture in fixtures:
            row = {**metadata.get(fixture.fixture_number, {}), **FixtureResponse.model_validate(fixture).model_dump()}
            row.update(round_number=rounds.get(fixture.round_id, 1))
            for key in ("home_team_id", "away_team_id", "venue_id"):
                row[key] = str(row[key]) if row[key] else None
            row.setdefault("stage", "knockout" if run.method == "knockout" else "league")
            row.setdefault("leg", 1)
            if not metadata and (run.configuration or {}).get("legs") == 2:
                row["leg"] = 2 if row["round_number"] > max(rounds.values(), default=1) // 2 else 1
            row.setdefault("group", None)
            row.setdefault("explanation", f"Saved {run.method.replace('_', ' ')} fixture; algorithm {run.algorithm_version}.")
            row.setdefault("home_source", None)
            row.setdefault("away_source", None)
            match = await self.session.get(Match, fixture.match_id) if fixture.match_id else None
            row["match_status"] = match.status if match else None
            row["immutable"] = fixture.is_locked or (await self.repo.match_started(match) if match else False)
            rows.append(row)
        by_id = {fixture.id: fixture.fixture_number for fixture in fixtures}
        for dependency in await self.repo.dependencies(run_id):
            for row in rows:
                if row["id"] == dependency.fixture_id:
                    row[f"{dependency.target_side}_source"] = f"{dependency.advancement}:{by_id[dependency.source_fixture_id]}"
        return run, fixtures, rows

    async def configuration(self, run, rows):
        stored = (run.configuration or {}).get("planning")
        if stored:
            return FixturePlanRequest.model_validate(stored)
        tournament = await self.repo.tournament(run.tournament_id)
        return FixturePlanRequest(method=run.method, format="knockout" if run.method == "knockout" else "round_robin",
            seed=run.seed, timezone=tournament.timezone, start_date=tournament.start_date, end_date=tournament.end_date,
            venue_ids=[venue.id for venue in await self.repo.venues(run.tournament_id)],
            legs=(run.configuration or {}).get("legs", 1), auto_schedule=False)

    async def report(self, run, rows):
        config = await self.configuration(run, rows)
        _, approved, availability, blackouts, external = await self.context(run.tournament_id, config, run.id)
        selected = [str(team) for team in config.team_ids] or approved
        teams = [team for team in selected if team in approved]
        result = analyze(rows, config, teams, groups=(run.configuration or {}).get("snapshot", {}).get("groups"), existing=external, extra_blackouts=blackouts)
        result["fixtures"] = rows
        if run.status == "draft" and any(row["status"] in {"cancelled", "postponed"} for row in rows):
            result["violations"].append(issue(None, "inactive_draft", "Reschedule postponed fixtures before publication. Create a new draw to replace cancelled draft fixtures."))
        for row in rows:
            if str(row["id"]) in (run.configuration or {}).get("reviews", {}):
                result["violations"].append(issue(row["fixture_number"], "result_review", (run.configuration or {})["reviews"][str(row["id"]) ]))
        self.check_availability(result, availability, run.tournament_id)
        return result

    async def workspace(self, tournament_id, run_id=None):
        tournament = await self.repo.tournament(tournament_id)
        if tournament is None:
            raise FixtureNotFoundError("Tournament not found.")
        runs = await self.repo.runs(tournament_id)
        selected = next((run for run in runs if run.id == run_id), None) if run_id else (runs[0] if runs else None)
        if run_id and not selected:
            raise FixtureNotFoundError("This generation does not belong to the tournament.")
        result = {"runs": [{"id": run.id, "method": run.method, "seed": run.seed, "status": run.status,
                            "algorithm_version": run.algorithm_version, "created_at": run.created_at} for run in runs], "selected_run": None}
        if selected:
            run, fixtures, rows = await self.load(selected.id)
            result.update(selected_run={**result["runs"][runs.index(selected)], "configuration": run.configuration,
                                        "versions": {str(row.id): row.version for row in fixtures}}, report=await self.report(run, rows))
        return result

    @staticmethod
    def versions(fixtures, expected):
        supplied = {str(key): value for key, value in expected.items()}
        actual = {str(row.id): row.version for row in fixtures}
        if actual != supplied:
            raise FixtureConflictError("The fixture plan changed. Refresh it before trying again.")

    async def create_match(self, fixture):
        if fixture.match_id or not fixture.home_team_id or not fixture.away_team_id or fixture.status != "published":
            return False
        defaults = {"players_per_side": 11, "minimum_players_to_start": None, "total_overs": None, "balls_per_over": 6, "innings_per_team": 1}
        run = await self.repo.run(fixture.generation_run_id)
        overs = (run.configuration or {}).get("planning", {}).get("overs") if run else None
        defaults["total_overs"] = overs
        config = await apply_tournament_fixture_rules(self.session, tournament_id=fixture.tournament_id,
            team_a_id=fixture.home_team_id, team_b_id=fixture.away_team_id, venue_id=fixture.venue_id,
            config=defaults, explicit_fields={"total_overs"} if overs is not None else set())
        match = Match(id=uuid4(), tournament_id=fixture.tournament_id, match_number=fixture.fixture_number,
            team_a_id=fixture.home_team_id, team_b_id=fixture.away_team_id, venue_id=fixture.venue_id,
            scheduled_at=fixture.scheduled_at, status=MatchStatus.DRAFT, match_type=MatchType.OTHER, **config)
        self.session.add(match)
        await self.session.flush()
        fixture.match_id = match.id
        self.log(fixture, "match_linked", {}, {"match_id": match.id}, "Organizer confirmed fixture publication")
        return True

    async def publish(self, run_id, expected_versions, reason):
        await self.repo.scheduling_lock()
        run, fixtures, rows = await self.load(run_id, True)
        if run.status == "published":
            return {"published_count": len(fixtures), "created_match_count": 0, "replayed": True}
        self.versions(fixtures, expected_versions)
        config = await self.configuration(run, rows)
        await self.context(run.tournament_id, config, run.id, lock=True)
        if run.status != "draft" or any(row.status != "draft" for row in fixtures):
            raise FixtureConflictError("Only a draft plan can be published.")
        report = await self.report(run, rows)
        if not report["valid"]:
            raise FixtureValidationError("Resolve fixture conflicts before publishing: " + "; ".join(item["message"] for item in report["violations"][:8]))
        now, created = datetime.now(timezone.utc), 0
        for fixture in fixtures:
            fixture.status, fixture.published_at = "published", now
            fixture.version += 1
            created += await self.create_match(fixture)
            self.log(fixture, "published", {"status": "draft"}, {"status": "published"}, reason)
        run.status, run.published_at = "published", now
        await self.session.flush()
        return {"published_count": len(fixtures), "created_match_count": created, "replayed": False}

    async def edit(self, run_id, payload):
        await self.repo.scheduling_lock()
        run, fixtures, rows = await self.load(run_id, True)
        if run.status != "draft":
            raise FixtureConflictError("Use reschedule for published fixtures.")
        await self.context(run.tournament_id, await self.configuration(run, rows), run.id, True)
        by_id = {row.id: row for row in fixtures}
        if len({change.fixture_id for change in payload.changes}) != len(payload.changes):
            raise FixtureValidationError("A fixture may occur only once in an edit batch.")
        for change in payload.changes:
            fixture = by_id.get(change.fixture_id)
            row = next((row for row in rows if row["id"] == change.fixture_id), None)
            if not fixture or fixture.version != change.expected_version or row["immutable"] or fixture.match_id:
                raise FixtureConflictError("A fixture changed, is locked, or is linked to a match. Refresh the plan.")
            changes = change.model_dump(exclude_unset=True, exclude={"fixture_id", "expected_version"})
            if not changes:
                raise FixtureValidationError("Supply at least one change.")
            for side in ("home", "away"):
                if f"{side}_team_id" in changes and row.get(f"{side}_source"):
                    raise FixtureValidationError("Bracket dependencies resolve through official results, not team overrides.")
            before = {key: getattr(fixture, key) for key in changes}
            for key, value in changes.items():
                setattr(fixture, key, value)
                row[key] = str(value) if key.endswith("_id") and value else value
            fixture.version += 1
            self.log(fixture, "edited", before, changes, payload.reason)
        report = await self.report(run, rows)
        hard = [item for item in report["violations"] if item["code"] not in {"unscheduled", "pairing", "missing_team"}]
        if hard:
            raise FixtureValidationError("; ".join(item["message"] for item in hard[:8]))
        await self.session.flush()
        return report

    async def action(self, fixture_id, payload):
        await self.repo.scheduling_lock()
        fixture = await self.session.get(Fixture, fixture_id)
        if fixture is None:
            raise FixtureNotFoundError("Fixture not found.")
        run, fixtures, rows = await self.load(fixture.generation_run_id, True)
        await self.context(run.tournament_id, await self.configuration(run, rows), run.id, True)
        fixture = next(row for row in fixtures if row.id == fixture_id)
        row = next(row for row in rows if row["id"] == fixture_id)
        match = await self.session.get(Match, fixture.match_id, with_for_update=True, populate_existing=True) if fixture.match_id else None
        if fixture.version != payload.expected_version:
            raise FixtureConflictError("Fixture version changed. Refresh before trying again.")
        if match and await self.repo.match_started(match):
            raise FixtureConflictError("Ready, live and completed matches are pinned and cannot be rewritten.")
        if fixture.is_locked and payload.action != "unlock":
            raise FixtureConflictError("Unlock this fixture before changing it.")
        before = {key: getattr(fixture, key) for key in ("status", "is_locked", "venue_id", "scheduled_at", "ends_at")}
        if payload.action == "review":
            assignments = {}
            for side in ("home", "away"):
                source = row.get(f"{side}_source")
                if not source:
                    continue
                if not source.startswith("winner:"):
                    raise FixtureValidationError("Official Stage 13 ranking resolution is still required.")
                parent = next((entry for entry in fixtures if entry.fixture_number == int(source.split(":")[1])), None)
                official = await self.session.get(Match, parent.match_id, populate_existing=True) if parent and parent.match_id else None
                if not official or official.status != MatchStatus.COMPLETED or not official.completed_at or official.winner_team_id not in {official.team_a_id, official.team_b_id}:
                    raise FixtureValidationError("The prerequisite still has no finalized winner.")
                assignments[f"{side}_team_id"] = official.winner_team_id
            for key, value in assignments.items():
                setattr(fixture, key, value)
            if match:
                match.team_a_id, match.team_b_id = fixture.home_team_id, fixture.away_team_id
            config = dict(run.configuration or {})
            reviews = dict(config.get("reviews", {}))
            reviews.pop(str(fixture.id), None)
            run.configuration = {**config, "reviews": reviews}
            for key, value in assignments.items():
                row[key] = str(value)
            checked = await self.report(run, rows)
            conflicts = [item for item in checked["violations"] if item["fixture_number"] in (None, fixture.fixture_number)]
            if conflicts:
                raise FixtureValidationError("; ".join(item["message"] for item in conflicts[:8]))
            self.log(fixture, "result_review_acknowledged", {}, assignments, payload.reason)
        elif payload.action in {"lock", "unlock"}:
            fixture.is_locked = payload.action == "lock"
        elif payload.action in {"postpone", "cancel"}:
            fixture.status = "postponed" if payload.action == "postpone" else "cancelled"
            fixture.scheduled_at = fixture.ends_at = None
            if match:
                match.scheduled_at = None
                if payload.action == "cancel":
                    match.status = MatchStatus.ABANDONED
        else:
            if fixture.status == "cancelled":
                raise FixtureConflictError("Cancelled fixtures cannot be rescheduled.")
            if not payload.scheduled_at or not payload.ends_at or not payload.venue_id:
                raise FixtureValidationError("Rescheduling requires a venue, start and end time.")
            fixture.scheduled_at, fixture.ends_at, fixture.venue_id = payload.scheduled_at, payload.ends_at, payload.venue_id
            fixture.status = "published" if run.status == "published" else "draft"
            row.update(scheduled_at=payload.scheduled_at, ends_at=payload.ends_at, venue_id=str(payload.venue_id), status=fixture.status)
            report = await self.report(run, rows)
            conflicts = [item for item in report["violations"] if item["fixture_number"] in (None, fixture.fixture_number) and item["code"] != "pairing"]
            if conflicts:
                raise FixtureValidationError("; ".join(item["message"] for item in conflicts[:8]))
            if match:
                match.scheduled_at, match.venue_id = fixture.scheduled_at, fixture.venue_id
        fixture.version += 1
        self.log(fixture, payload.action, before, {key: getattr(fixture, key) for key in before}, payload.reason)
        await self.session.flush()
        return {"fixture_id": fixture.id, "version": fixture.version}

    async def progress(self, run_id):
        await self.repo.scheduling_lock()
        run, fixtures, rows = await self.load(run_id, True)
        by_number = {row.fixture_number: row for row in fixtures}
        config = dict(run.configuration or {})
        reviews = dict(config.get("reviews", {}))
        changed, blocked = 0, []
        for row in sorted(rows, key=lambda row: (row["round_number"], row["fixture_number"])):
            fixture = by_number[row["fixture_number"]]
            if fixture.status in {"cancelled", "postponed"}:
                continue
            for side in ("home", "away"):
                source = row.get(f"{side}_source")
                if not source:
                    continue
                winner = None
                if source.startswith(("winner:", "loser:")):
                    parent = by_number.get(int(source.split(":")[1]))
                    match = await self.session.get(Match, parent.match_id) if parent and parent.match_id else None
                    if match and match.status == MatchStatus.COMPLETED and match.completed_at and match.winner_team_id in {match.team_a_id, match.team_b_id}:
                        winner = match.winner_team_id if source.startswith("winner:") else (match.team_b_id if match.winner_team_id == match.team_a_id else match.team_a_id)
                if winner is None:
                    blocked.append({"fixture_number": fixture.fixture_number, "source": source,
                                    "message": "Official Stage 13 rankings required." if source.startswith("group:") else "Awaiting a finalized winner; ties, reopened results and no-results block advancement."})
                previous = getattr(fixture, f"{side}_team_id")
                if previous != winner:
                    if fixture.match_id or fixture.is_locked:
                        message = "A prerequisite result changed or reopened. Review this dependent match before activation."
                        if reviews.get(str(fixture.id)) != message:
                            self.log(fixture, "result_review_required", {f"{side}_team_id": previous}, {"expected_team_id": winner}, message)
                        reviews[str(fixture.id)] = message
                    else:
                        setattr(fixture, f"{side}_team_id", winner)
                        fixture.version += 1
                        changed += 1
                        self.log(fixture, "bracket_resolved", {f"{side}_team_id": previous}, {f"{side}_team_id": winner}, "Official finalized result")
        config["reviews"] = reviews
        run.configuration = config
        if run.status == "published" and any(not row.match_id for row in fixtures):
            report_rows = [{**entry, "home_team_id": str(by_number[entry["fixture_number"]].home_team_id) if by_number[entry["fixture_number"]].home_team_id else None,
                            "away_team_id": str(by_number[entry["fixture_number"]].away_team_id) if by_number[entry["fixture_number"]].away_team_id else None} for entry in rows]
            report = await self.report(run, report_rows)
            for fixture in fixtures:
                if str(fixture.id) not in reviews and not any(item["fixture_number"] in (None, fixture.fixture_number) for item in report["violations"]):
                    changed += await self.create_match(fixture)
        await self.session.flush()
        return {"changed_count": changed, "blocked": blocked, "reviews": reviews}

    async def regenerate(self, run_id, payload):
        await self.repo.scheduling_lock()
        run, fixtures, rows = await self.load(run_id, True)
        self.versions(fixtures, payload.expected_versions)
        previous = await self.configuration(run, rows)
        config = payload.configuration
        schedule_fields = {"start_date", "end_date", "final_date", "timezone", "weekdays", "times", "duration_minutes",
                           "minimum_rest_minutes", "blackouts", "venue_ids", "auto_schedule", "request_id"}
        if previous.model_dump(exclude=schedule_fields) != config.model_dump(exclude=schedule_fields):
            raise FixtureValidationError("Partial regeneration changes allocations only. Edit draft opponents separately.")
        _, _, _, blackouts, external = await self.context(run.tournament_id, config, run.id, True)
        editable = [row for row in rows if not row["immutable"] and row["status"] not in {"cancelled", "completed"}]
        pinned = [scheduled(row) for row in rows if row not in editable and row.get("scheduled_at") and row.get("ends_at") and row.get("venue_id")]
        proposals = [{**row, "scheduled_at": None, "ends_at": None, "venue_id": None} for row in editable]
        conflicts = allocate_rows(config, proposals, existing=[*external, *pinned], extra_blackouts=blackouts)
        if conflicts:
            raise FixtureValidationError("No feasible partial schedule: " + "; ".join(item["message"] for item in conflicts[:5]))
        proposed = {row["id"]: row for row in proposals}
        merged = [proposed.get(row["id"], row) for row in rows]
        saved = dict(run.configuration or {})
        run.configuration = {**saved, "planning": config.model_dump(mode="json", exclude={"request_id"})}
        report = await self.report(run, merged)
        hard = [item for item in report["violations"] if item["code"] not in {"pairing", "result_review"}]
        if hard:
            raise FixtureValidationError("; ".join(item["message"] for item in hard[:8]))
        for fixture in fixtures:
            if fixture.id not in proposed:
                continue
            row = proposed[fixture.id]
            before = {key: getattr(fixture, key) for key in ("scheduled_at", "ends_at", "venue_id")}
            fixture.scheduled_at, fixture.ends_at, fixture.venue_id = row["scheduled_at"], row["ends_at"], UUID(row["venue_id"])
            fixture.version += 1
            if fixture.match_id:
                match = await self.session.get(Match, fixture.match_id, with_for_update=True, populate_existing=True)
                if await self.repo.match_started(match):
                    raise FixtureConflictError("A match started while regenerating. Refresh the plan.")
                match.scheduled_at, match.venue_id = fixture.scheduled_at, fixture.venue_id
            self.log(fixture, "regenerated", before, {key: getattr(fixture, key) for key in before}, "Organizer regenerated unplayed allocations; pinned fixtures preserved")
        await self.session.flush()
        return {"updated_count": len(proposals), "pinned_count": len(rows) - len(proposals)}


async def validate_fixture_activation(session, match):
    """Guard linked Match readiness when a dependency reopens or is disputed."""
    from sqlalchemy import select
    from app.core.exceptions import ConflictError
    fixture = await session.scalar(select(Fixture).where(Fixture.match_id == match.id))
    if fixture is None:
        return
    service = FixturePlanningService(session)
    run, _, rows = await service.load(fixture.generation_run_id)
    row = next(row for row in rows if row["id"] == fixture.id)
    if fixture.status != "published" or str(fixture.id) in (run.configuration or {}).get("reviews", {}):
        raise ConflictError("This fixture is postponed, cancelled, or requires bracket review.")
    for side in ("home", "away"):
        source = row.get(f"{side}_source")
        if not source:
            continue
        if not source.startswith("winner:"):
            raise ConflictError("Official group ranking resolution is required before activation.")
        parent = next((entry for entry in rows if entry["fixture_number"] == int(source.split(":")[1])), None)
        official = await session.get(Match, parent["match_id"]) if parent and parent["match_id"] else None
        if not official or official.status != MatchStatus.COMPLETED or not official.completed_at or official.winner_team_id != getattr(fixture, f"{side}_team_id"):
            raise ConflictError("A prerequisite result is unresolved or changed. Review the bracket before activation.")
