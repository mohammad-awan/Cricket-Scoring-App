"""Qualification and bracket-slot resolution.

Teams are never promoted prematurely:

* A team is ``qualified`` before its group finishes only when it has
  mathematically clinched a top-k place (fewer than k rivals can still
  reach its current points), and ``eliminated`` only when k rivals
  already have more points than it can still reach.
* Once a group is complete, places are ``confirmed`` unless a tie
  straddles the qualification boundary; such a tie stays
  ``awaiting_adjudication`` until an organizer records a placement.
* A knockout slot fed by ``group:<name>:<rank>`` resolves only when that
  exact position is final and unambiguous.
"""

from __future__ import annotations
from fractions import Fraction
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, ValidationError
from app.models import Match, MatchStatus
from app.models.entities.fixtures import FixtureGenerationRun
from app.services.tournament_results import (
    LEAGUE_STAGES,
    current_dispositions,
    published_fixtures,
    resolve_outcome,
)
from app.services.tournament_standings import calculate_tournament_standings, get_standings_rules


def group_team_status(rows: list[dict], remaining: dict, top_k: int, win_points: int, complete: bool) -> dict:
    """Pure per-team qualification status for one group table."""

    statuses = {}
    boundary_rank = None

    if complete and len(rows) > top_k:
        boundary = rows[top_k - 1]
        after = rows[top_k]
        if boundary["rank"] == after["rank"]:
            boundary_rank = boundary["rank"]

    for row in rows:
        team_id = row["team_id"]

        if complete:
            if boundary_rank is not None and row["rank"] == boundary_rank:
                statuses[team_id] = "awaiting_adjudication"
            elif row["rank"] <= top_k:
                statuses[team_id] = "qualified"
            else:
                statuses[team_id] = "eliminated"
            continue

        maximum = row["points"] + remaining.get(team_id, 0) * win_points
        rivals_reaching = sum(
            1 for other in rows
            if other["team_id"] != team_id
            and other["points"] + remaining.get(other["team_id"], 0) * win_points >= row["points"]
        )
        rivals_above = sum(
            1 for other in rows
            if other["team_id"] != team_id and other["points"] > maximum
        )

        if rivals_reaching < top_k:
            statuses[team_id] = "qualified"
        elif rivals_above >= top_k:
            statuses[team_id] = "eliminated"
        else:
            statuses[team_id] = "in_contention"

    return statuses


def cross_group_key(row: dict, breakers: list[str]):
    """Comparable key across groups; head-to-head cannot apply between groups."""

    key = []
    for breaker in breakers:
        if breaker == "points":
            key.append(row["points"])
        elif breaker == "wins":
            key.append(row["won"])
        elif breaker == "net_run_rate":
            key.append(Fraction(row["net_run_rate_exact"]))
        elif breaker == "wickets":
            key.append(row["wickets_taken"])
    return tuple(key)


def best_ranked(groups: list[dict], rank: int, count: int, breakers: list[str]) -> dict:
    candidates, waiting = [], []

    for group in groups:
        row = next((item for item in group["standings"] if item["rank"] == rank and not item["ranking_unresolved"]), None)

        if group["status"] != "confirmed" or row is None:
            waiting.append(group["group_name"])
            continue

        candidates.append({**row, "group_name": group["group_name"]})

    candidates.sort(key=lambda row: cross_group_key(row, breakers), reverse=True)
    boundary_tie = (
        len(candidates) > count
        and cross_group_key(candidates[count - 1], breakers) == cross_group_key(candidates[count], breakers)
    )

    if waiting:
        status = "awaiting_results"
    elif boundary_tie:
        status = "awaiting_adjudication"
    else:
        status = "confirmed"

    return {
        "rank": rank,
        "count": count,
        "status": status,
        "ranking": candidates,
        "qualifiers": candidates[:count] if status == "confirmed" else [],
        "waiting_on_groups": waiting,
        "comparison_keys": [breaker for breaker in breakers if breaker not in {"head_to_head", "drawing_of_lots"}],
    }


async def default_top_k(session: AsyncSession, tournament_id: UUID) -> int:
    runs = (
        await session.scalars(
            select(FixtureGenerationRun).where(
                FixtureGenerationRun.tournament_id == tournament_id,
                FixtureGenerationRun.status == "published",
            )
        )
    ).all()

    for run in runs:
        value = (run.configuration or {}).get("planning", {}).get("advance_per_group")
        if value:
            return int(value)

    return 2


async def tournament_qualification(
    session: AsyncSession,
    tournament_id: UUID,
    top_k: int | None = None,
    *,
    best_rank: int | None = None,
    best_count: int = 0,
) -> dict:
    if top_k is None:
        top_k = await default_top_k(session, tournament_id)

    if top_k < 1:
        raise ValidationError("Qualification count must be positive")

    standings = await calculate_tournament_standings(session, tournament_id)
    _, rules = await get_standings_rules(session, tournament_id)
    fixtures = await published_fixtures(session, tournament_id)
    pending_ids = set(standings["pending_fixtures"]) | set(standings["disputed_fixtures"])

    remaining: dict = {}
    for item in fixtures:
        if item.stage in LEAGUE_STAGES and str(item.fixture.id) in pending_ids:
            for team_id in (item.fixture.home_team_id, item.fixture.away_team_id):
                if team_id is not None:
                    remaining[team_id] = remaining.get(team_id, 0) + 1

    groups, blockers = [], []

    for table in standings["tables"]:
        rows = table["standings"]
        group_pending = sum(remaining.get(row["team_id"], 0) for row in rows) // 2
        complete = group_pending == 0
        statuses = group_team_status(rows, remaining, top_k, rules.points.win, complete)

        if len(rows) < top_k:
            blockers.append(f"{table['group_name']}: only {len(rows)} team(s) for {top_k} qualifying place(s)")

        if not complete:
            status = "awaiting_results"
            blockers.append(f"{table['group_name']}: {group_pending} fixture(s) awaiting an official result")
        elif "awaiting_adjudication" in statuses.values():
            status = "awaiting_adjudication"
            blockers.append(f"{table['group_name']}: unresolved tie at the qualification boundary requires an adjudicated placement")
        else:
            status = "confirmed"

        groups.append({
            "group_key": table["group_key"],
            "group_id": table["group_id"],
            "group_name": table["group_name"],
            "status": status,
            "remaining_fixtures": group_pending,
            "standings": [
                {**row, "qualification_status": statuses[row["team_id"]], "remaining_fixtures": remaining.get(row["team_id"], 0)}
                for row in rows
            ],
            "qualifiers": [row for row in rows if statuses[row["team_id"]] == "qualified"],
        })

    best = None
    if best_rank and best_count:
        best = best_ranked(groups, best_rank, best_count, standings["tie_breakers"])
        if best["status"] != "confirmed":
            blockers.append(f"Best {best_count} team(s) ranked {best_rank}: {best['status'].replace('_', ' ')}")

    resolver = SlotResolver(session, tournament_id, groups=groups)
    slots = []

    for item in fixtures:
        for side in ("home", "away"):
            source = getattr(item, f"{side}_source")
            if not source or not source.startswith("group:"):
                continue
            team_id, message = await resolver.resolve(source, {})
            slots.append({
                "fixture_id": item.fixture.id,
                "fixture_number": item.fixture.fixture_number,
                "side": side,
                "source": source,
                "resolved_team_id": team_id,
                "assigned_team_id": getattr(item.fixture, f"{side}_team_id"),
                "status": "resolved" if team_id else "awaiting",
                "message": message,
            })

    return {
        "tournament_id": tournament_id,
        "ruleset_id": standings["ruleset_id"],
        "ruleset_version": standings["ruleset_version"],
        "ruleset_checksum": standings["ruleset_checksum"],
        "top_k": top_k,
        "pending_fixtures": standings["pending_fixtures"],
        "disputed_fixtures": standings["disputed_fixtures"],
        "groups": groups,
        "best_ranked": best,
        "knockout_slots": slots,
        "blockers": blockers,
        "advancement_permitted": not blockers,
    }


# Backwards-compatible name used by earlier Stage 13 routes.
async def group_qualification(session: AsyncSession, tournament_id: UUID, top_k: int = 2) -> dict:
    return await tournament_qualification(session, tournament_id, top_k)


class SlotResolver:
    """Resolve Stage 12 bracket sources from official Stage 13 results.

    Supported sources: ``winner:<fixture_number>``,
    ``loser:<fixture_number>`` and ``group:<group name>:<rank>``.
    """

    def __init__(self, session: AsyncSession, tournament_id: UUID, *, groups: list[dict] | None = None):
        self.session = session
        self.tournament_id = tournament_id
        self._groups = groups
        self._dispositions = None

    async def groups(self) -> list[dict]:
        if self._groups is None:
            try:
                self._groups = (await tournament_qualification(self.session, self.tournament_id))["groups"]
            except ConflictError:
                self._groups = []
        return self._groups

    async def dispositions(self) -> dict:
        if self._dispositions is None:
            self._dispositions = await current_dispositions(self.session, self.tournament_id)
        return self._dispositions

    async def resolve(self, source: str, fixtures_by_number: dict) -> tuple[UUID | None, str]:
        if source.startswith(("winner:", "loser:")):
            kind, number = source.split(":", 1)
            parent = fixtures_by_number.get(int(number))

            if parent is None:
                return None, "Source fixture not found."

            match = await self.session.get(Match, parent.match_id) if parent.match_id else None
            # A scored (completed) match can never carry a disposition.
            disposition = (
                None
                if match is not None and match.status == MatchStatus.COMPLETED
                else (await self.dispositions()).get(parent.id)
            )
            outcome = resolve_outcome(
                getattr(parent, "home_team_id", None),
                getattr(parent, "away_team_id", None),
                match,
                disposition,
            )

            advancing = outcome.advancing_team_id

            if advancing is None:
                return None, "Awaiting a finalized winner; ties, reopened results and no-results need an advancement adjudication."

            teams = {getattr(parent, "home_team_id", None), getattr(parent, "away_team_id", None)}
            if outcome.has_winner:
                teams |= {outcome.winner_team_id, outcome.loser_team_id}
            losing = next((team for team in teams if team is not None and team != advancing), None)
            return (advancing if kind == "winner" else losing), "Resolved from the official result."

        if source.startswith("group:"):
            name, _, rank = source[len("group:"):].rpartition(":")

            if not name or not rank.isdigit():
                return None, "Malformed group source."

            group = next((item for item in await self.groups() if item["group_name"] == name), None)

            if group is None:
                return None, f"Group {name} has no official standings."

            if group["remaining_fixtures"]:
                return None, f"Group {name} still has fixtures awaiting official results."

            row = next((item for item in group["standings"] if item["rank"] == int(rank)), None)

            if row is None or row["ranking_unresolved"]:
                return None, f"Position {rank} in group {name} requires an adjudicated placement."

            return row["team_id"], "Resolved from the final official group table."

        return None, "Unsupported bracket source."
