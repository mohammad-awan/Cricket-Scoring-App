"""Tournament headquarters and live operations.

Every fixture is linked to the existing match setup, live scoring,
corrections, scorecard and WebSocket endpoints; there is no tournament
specific scoring engine.
"""

from __future__ import annotations
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    Innings,
    MatchPlayer,
    MatchStatus,
    Team,
    Tournament,
    TournamentGroup,
    TournamentTeam,
    Venue,
)
from app.models.entities.tournaments import TournamentAsset, TournamentVenue
from app.services.tournament_bracket_review import review_bracket
from app.services.tournament_results import (
    LEAGUE_STAGES,
    fixture_outcomes,
    published_fixtures,
    result_text,
)
from app.services.tournament_standings import get_standings_rules


LIVE_STATUSES = {MatchStatus.LIVE, MatchStatus.INNINGS_BREAK}


def match_links(match_id: UUID | None) -> dict:
    if match_id is None:
        return {}
    return {
        "match_setup": f"/match-setup/{match_id}",
        "live_scoring": f"/live-scoring/{match_id}",
        "corrections": f"/live-scoring/{match_id}",
        "live_viewer": f"/live-viewer/{match_id}",
        "scorecard": f"/scorecard/{match_id}",
        "scorecard_api": f"/matches/{match_id}/scorecard",
        "scoring_state_api": f"/matches/{match_id}/scoring",
        "websocket": f"/matches/{match_id}/live",
    }


async def _context(session: AsyncSession, tournament_id: UUID) -> dict:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    fixtures = await published_fixtures(session, tournament_id)
    outcomes, match_map = await fixture_outcomes(session, tournament_id, fixtures)
    team_ids = {team for item in fixtures for team in (item.fixture.home_team_id, item.fixture.away_team_id) if team}
    team_ids |= set((await session.scalars(select(TournamentTeam.team_id).where(TournamentTeam.tournament_id == tournament_id))).all())
    names = dict((await session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()) if team_ids else {}
    for membership in (await session.scalars(select(TournamentTeam).where(TournamentTeam.tournament_id == tournament_id))).all():
        if membership.display_name:
            names[membership.team_id] = membership.display_name
    venue_ids = {item.fixture.venue_id for item in fixtures if item.fixture.venue_id}
    venues = dict((await session.execute(select(Venue.id, Venue.name).where(Venue.id.in_(venue_ids)))).all()) if venue_ids else {}

    live_ids = [match.id for match in match_map.values() if match.status in LIVE_STATUSES | {MatchStatus.COMPLETED}]
    scores = defaultdict(list)
    if live_ids:
        for innings in (
            await session.scalars(select(Innings).where(Innings.match_id.in_(live_ids)).order_by(Innings.innings_number))
        ).all():
            bpo = match_map[innings.match_id].balls_per_over
            scores[innings.match_id].append({
                "innings_number": innings.innings_number,
                "team_id": innings.batting_team_id,
                "team_name": names.get(innings.batting_team_id),
                "score": f"{innings.total_runs}/{innings.wickets}",
                "overs": f"{innings.legal_balls // bpo}.{innings.legal_balls % bpo}",
                "status": innings.status.value if hasattr(innings.status, "value") else innings.status,
            })

    return {
        "tournament": tournament, "fixtures": fixtures, "outcomes": outcomes, "matches": match_map,
        "names": names, "venues": venues, "scores": scores,
    }


def _fixture_row(context: dict, item) -> dict:
    fixture = item.fixture
    match = context["matches"].get(fixture.match_id)
    outcome = context["outcomes"][fixture.id]
    names = context["names"]
    return {
        "fixture_id": fixture.id,
        "fixture_number": fixture.fixture_number,
        "round_number": item.round_number,
        "stage": item.stage,
        "group_name": item.group_name,
        "home_team_id": fixture.home_team_id,
        "home_team_name": names.get(fixture.home_team_id) or item.home_source,
        "away_team_id": fixture.away_team_id,
        "away_team_name": names.get(fixture.away_team_id) or item.away_source,
        "home_source": item.home_source,
        "away_source": item.away_source,
        "venue_id": fixture.venue_id,
        "venue_name": context["venues"].get(fixture.venue_id),
        "scheduled_at": fixture.scheduled_at,
        "ends_at": fixture.ends_at,
        "fixture_status": fixture.status,
        "is_locked": fixture.is_locked,
        "version": fixture.version,
        "match_id": fixture.match_id,
        "match_status": match.status.value if match else None,
        "outcome": outcome.outcome,
        "winner_team_id": outcome.winner_team_id,
        "advancing_team_id": outcome.advancing_team_id,
        "result": result_text(outcome, names) if outcome.is_final or outcome.outcome == "disputed" else None,
        "disposition": outcome.disposition,
        "review_required": item.review_message,
        "innings": context["scores"].get(fixture.match_id, []),
        "links": match_links(fixture.match_id),
    }


async def get_tournament_overview(session: AsyncSession, tournament_id: UUID) -> dict:
    context = await _context(session, tournament_id)
    tournament = context["tournament"]
    rows = [_fixture_row(context, item) for item in context["fixtures"]]

    memberships = (await session.scalars(select(TournamentTeam).where(TournamentTeam.tournament_id == tournament_id))).all()
    groups = {group.id: group.name for group in (await session.scalars(select(TournamentGroup).where(TournamentGroup.tournament_id == tournament_id))).all()}
    planner_groups = {}
    for item in context["fixtures"]:
        if item.group_name:
            planner_groups.setdefault(item.group_name, set()).update(
                team for team in (item.fixture.home_team_id, item.fixture.away_team_id) if team
            )
    venues = (
        await session.execute(
            select(Venue.id, Venue.name)
            .join(TournamentVenue, TournamentVenue.venue_id == Venue.id)
            .where(TournamentVenue.tournament_id == tournament_id)
        )
    ).all()
    assets = (
        await session.scalars(
            select(TournamentAsset).where(TournamentAsset.tournament_id == tournament_id, TournamentAsset.is_current.is_(True))
        )
    ).all()

    rules = None
    try:
        version, parsed = await get_standings_rules(session, tournament_id)
        rules = {
            "version": version.version, "format_code": parsed.format_code, "structure": parsed.structure,
            "overs_per_innings": parsed.overs_per_innings, "balls_per_over": parsed.balls_per_over,
            "players_per_side": parsed.players_per_side, "points": parsed.points.model_dump(),
            "tie_breakers": list(parsed.tie_breakers),
        }
    except ConflictError:
        pass

    now = datetime.now(UTC)
    live = [row for row in rows if row["match_status"] in {"live", "innings_break"}]
    upcoming = sorted(
        [row for row in rows if row["outcome"] == "pending" and row["match_status"] not in {"live", "innings_break"} and row["fixture_status"] == "published"],
        key=lambda row: (row["scheduled_at"] is None, row["scheduled_at"] or now),
    )
    completed = sorted(
        [row for row in rows if row["outcome"] not in {"pending", "excluded"}],
        key=lambda row: (row["scheduled_at"] is None, row["scheduled_at"] or now), reverse=True,
    )

    return {
        "tournament": {
            "id": tournament.id, "name": tournament.name, "season": tournament.season,
            "organizer": tournament.organizer, "description": tournament.description,
            "terms": tournament.terms, "trophy_name": tournament.trophy_name, "location": tournament.location,
            "timezone": tournament.timezone, "status": tournament.status.value,
            "start_date": tournament.start_date, "end_date": tournament.end_date,
            "logo_url": next((f"/tournaments/{tournament_id}/assets/logo" for asset in assets if asset.kind == "logo"), None),
            "cover_url": next((f"/tournaments/{tournament_id}/assets/cover" for asset in assets if asset.kind == "cover"), None),
        },
        "rules": rules,
        "venues": [{"venue_id": venue_id, "name": name} for venue_id, name in venues],
        "teams": {
            "total": len(memberships),
            "approved": sum(membership.registration_status == "approved" for membership in memberships),
            "items": [
                {"team_id": membership.team_id, "team_name": context["names"].get(membership.team_id),
                 "registration_status": membership.registration_status, "is_reserve": membership.is_reserve,
                 "group_name": groups.get(membership.group_id) or next((name for name, members in planner_groups.items() if membership.team_id in members), None)}
                for membership in memberships
            ],
        },
        "groups": sorted(set(groups.values()) | set(planner_groups)),
        "fixtures": {"total": len(rows), "by_status": dict(Counter(row["fixture_status"] for row in rows)),
                     "by_outcome": dict(Counter(row["outcome"] for row in rows))},
        "matches": {"total": len(context["matches"]), "by_status": dict(Counter(match.status.value for match in context["matches"].values()))},
        "live": live,
        "upcoming": upcoming[:10],
        "recent_results": completed[:10],
        "quick_links": {
            "schedule": f"/tournaments/{tournament_id}/calendar",
            "results": f"/tournaments/{tournament_id}/results",
            "standings": f"/tournaments/{tournament_id}/standings",
            "fixture_builder": f"/competitions/{tournament_id}/fixtures",
            "tournament_websocket": f"/tournaments/{tournament_id}/live/ws",
        },
    }


async def tournament_live(session: AsyncSession, tournament_id: UUID) -> dict:
    context = await _context(session, tournament_id)
    rows = [_fixture_row(context, item) for item in context["fixtures"]]
    return {
        "tournament_id": tournament_id,
        "live": [row for row in rows if row["match_status"] in {"live", "innings_break"}],
        "next": sorted(
            [row for row in rows if row["outcome"] == "pending" and row["fixture_status"] == "published" and row["match_status"] not in {"live", "innings_break"}],
            key=lambda row: (row["scheduled_at"] is None, str(row["scheduled_at"] or "")),
        )[:5],
        "websocket": f"/tournaments/{tournament_id}/live/ws",
    }


async def tournament_results(session: AsyncSession, tournament_id: UUID) -> dict:
    context = await _context(session, tournament_id)
    rows = [_fixture_row(context, item) for item in context["fixtures"] if context["outcomes"][item.fixture.id].outcome not in {"pending"}]
    rows.sort(key=lambda row: (str(row["scheduled_at"] or ""), row["fixture_number"]), reverse=True)
    return {"tournament_id": tournament_id, "results": rows}


async def tournament_calendar(session: AsyncSession, tournament_id: UUID, *, team_id: UUID | None = None, venue_id: UUID | None = None) -> dict:
    context = await _context(session, tournament_id)
    try:
        zone = ZoneInfo(context["tournament"].timezone or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")

    days = defaultdict(list)
    unscheduled = []
    for item in context["fixtures"]:
        fixture = item.fixture
        if team_id and team_id not in {fixture.home_team_id, fixture.away_team_id}:
            continue
        if venue_id and fixture.venue_id != venue_id:
            continue
        row = _fixture_row(context, item)
        if fixture.scheduled_at is None:
            unscheduled.append(row)
        else:
            days[fixture.scheduled_at.astimezone(zone).date().isoformat()].append(row)

    return {
        "tournament_id": tournament_id,
        "timezone": str(zone),
        "days": [
            {"date": day, "fixtures": sorted(items, key=lambda row: (row["scheduled_at"], row["fixture_number"]))}
            for day, items in sorted(days.items())
        ],
        "unscheduled": unscheduled,
    }


async def operations_board(session: AsyncSession, tournament_id: UUID) -> dict:
    """Organizer intervention board."""

    context = await _context(session, tournament_id)
    rows = [_fixture_row(context, item) for item in context["fixtures"]]
    now = datetime.now(UTC)
    match_ids = [row["match_id"] for row in rows if row["match_id"]]
    selections = defaultdict(dict)
    if match_ids:
        for match_id, team_id, count in (
            await session.execute(
                select(MatchPlayer.match_id, MatchPlayer.team_id, func.count(MatchPlayer.id))
                .where(MatchPlayer.match_id.in_(match_ids))
                .group_by(MatchPlayer.match_id, MatchPlayer.team_id)
            )
        ).all():
            selections[match_id][team_id] = count

    alerts = []

    def alert(severity, code, row, message, action):
        alerts.append({"severity": severity, "code": code, "fixture_id": row["fixture_id"], "fixture_number": row["fixture_number"],
                       "match_id": row["match_id"], "message": message, "action": action, "links": row["links"]})

    readiness = []
    for row in rows:
        if row["outcome"] in {"excluded"}:
            continue
        match = context["matches"].get(row["match_id"])
        label = f"Fixture {row['fixture_number']} ({row['home_team_name']} v {row['away_team_name']})"

        if row["fixture_status"] == "published" and (not row["venue_id"] or not row["scheduled_at"]) and row["outcome"] == "pending":
            alert("warning", "unscheduled", row, f"{label} has no venue or time", "Assign a venue and time in the fixture builder")
        if row["review_required"]:
            alert("danger", "bracket_review", row, f"{label}: {row['review_required']}", "Review the bracket slot before activation")
        if row["outcome"] == "disputed":
            alert("danger", "disputed_result", row, f"{label} completed without a valid result", "Review the scorecard and correct the result")
        if row["fixture_status"] == "postponed":
            alert("warning", "postponed", row, f"{label} is postponed", "Reschedule it or record a disposition")
        if row["outcome"] == "abandoned" and row["disposition"] is None:
            alert("info", "abandoned", row, f"{label} was abandoned", "Confirm the disposition (abandoned or no result)")
        if row["stage"] not in LEAGUE_STAGES and row["outcome"] in {"tie", "abandoned", "no_result"} and row["advancing_team_id"] is None:
            alert("danger", "knockout_unresolved", row, f"{label} produced no winner", "Record an advancement adjudication")
        if (
            row["outcome"] == "pending" and match is not None and match.status not in LIVE_STATUSES
            and row["ends_at"] is not None and row["ends_at"] < now
        ):
            alert("danger", "unsubmitted_scorecard", row, f"{label} ended at {row['ends_at'].isoformat()} without an official result",
                  "Complete scoring or record a disposition")
        if match is not None and match.status in LIVE_STATUSES and row["ends_at"] is not None and row["ends_at"] + timedelta(hours=2) < now:
            alert("warning", "overrunning", row, f"{label} is still live well past its scheduled end", "Check with the scorer")

        if match is not None and match.status in {MatchStatus.DRAFT, MatchStatus.READY} and row["outcome"] == "pending":
            counts = selections.get(match.id, {})
            minimum = match.minimum_players_to_start or match.players_per_side
            issues = []
            for team in (match.team_a_id, match.team_b_id):
                if counts.get(team, 0) < minimum:
                    issues.append(f"{context['names'].get(team)} has {counts.get(team, 0)}/{minimum} players selected")
            if match.toss_winner_id is None:
                issues.append("Toss not recorded")
            readiness.append({**row, "readiness": "ready" if match.status == MatchStatus.READY else "setup_incomplete", "issues": issues})
            if (
                match.status == MatchStatus.DRAFT and row["scheduled_at"] is not None
                and now <= row["scheduled_at"] <= now + timedelta(hours=24)
            ):
                alert("warning", "match_not_ready", row, f"{label} starts within 24 hours and is not ready", "Complete match setup")

    bracket = await review_bracket(session, tournament_id)
    for item in bracket["dependencies"]:
        if item["status"] in {"requires_review", "locked_conflict", "invalid_dependency"}:
            alerts.append({"severity": "danger", "code": f"bracket_{item['status']}", "fixture_id": item["target_fixture_id"],
                           "fixture_number": None, "match_id": None, "message": f"Bracket dependency {item['status'].replace('_', ' ')}",
                           "action": "Review the bracket", "links": {}})

    by_status = defaultdict(list)
    for row in rows:
        key = row["match_status"] if row["match_status"] in {"live", "innings_break"} else (
            "completed" if row["outcome"] not in {"pending", "disputed"} else row["fixture_status"]
        )
        by_status[key].append(row)

    severity = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda item: (severity[item["severity"]], item["fixture_number"] or 0))
    return {
        "tournament_id": tournament_id,
        "generated_at": now,
        "summary": {key: len(value) for key, value in by_status.items()},
        "fixtures_by_status": by_status,
        "venue_assignment": {
            "unassigned": [row for row in rows if not row["venue_id"] and row["outcome"] == "pending" and row["fixture_status"] == "published"],
            "by_venue": dict(Counter(row["venue_name"] or "Unassigned" for row in rows if row["outcome"] != "excluded")),
        },
        "match_readiness": readiness,
        "unsubmitted_scorecards": [item for item in alerts if item["code"] == "unsubmitted_scorecard"],
        "disputed_outcomes": [item for item in alerts if item["code"] in {"disputed_result", "knockout_unresolved", "bracket_review"}],
        "postponed": [row for row in rows if row["fixture_status"] == "postponed"],
        "abandoned": [row for row in rows if row["outcome"] in {"abandoned", "no_result"}],
        "alerts": alerts,
    }


async def tournament_bracket(session: AsyncSession, tournament_id: UUID) -> dict:
    context = await _context(session, tournament_id)
    knockout = [item for item in context["fixtures"] if item.stage not in LEAGUE_STAGES]
    rounds = defaultdict(list)
    for item in knockout:
        rounds[item.round_number].append(_fixture_row(context, item))

    total = len(rounds)
    labels = {}
    for index, number in enumerate(sorted(rounds)):
        remaining = total - index
        labels[number] = {1: "Final", 2: "Semi-finals", 3: "Quarter-finals"}.get(remaining, f"Round {index + 1}")

    review = await review_bracket(session, tournament_id)
    return {
        "tournament_id": tournament_id,
        "rounds": [
            {"round_number": number, "name": labels[number], "fixtures": sorted(rows, key=lambda row: row["fixture_number"])}
            for number, rows in sorted(rounds.items())
        ],
        "dependency_review": review,
    }


async def tournament_groups(session: AsyncSession, tournament_id: UUID) -> dict:
    from app.services.tournament_qualification import tournament_qualification

    qualification = await tournament_qualification(session, tournament_id)
    context = await _context(session, tournament_id)
    fixtures_by_group = defaultdict(list)
    for item in context["fixtures"]:
        if item.stage in LEAGUE_STAGES:
            fixtures_by_group[item.group_name or "League"].append(_fixture_row(context, item))

    return {
        "tournament_id": tournament_id,
        "top_k": qualification["top_k"],
        "groups": [
            {**group, "fixtures": fixtures_by_group.get(group["group_name"], [])}
            for group in qualification["groups"]
        ],
        "best_ranked": qualification["best_ranked"],
        "knockout_slots": qualification["knockout_slots"],
    }
