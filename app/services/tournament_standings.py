"""Tournament points tables.

Conventions (returned with every table so consumers can display them):

* Only official results count (see ``tournament_results``): completed
  scored matches plus organizer dispositions. Pending fixtures never
  contribute.
* Net run rate = (runs scored / overs faced) - (runs conceded / overs
  bowled). Overs are exact fractions ``legal_balls / balls_per_over``,
  never cricket notation (4.3 overs = 4.5 overs).
* All-out: under the ``full_quota`` policy a side bowled out is charged
  its full overs quota (the match's ``total_overs``). When a match has
  no fixed quota the overs actually faced are used.
* Interrupted / reduced matches: the quota is the match's configured
  ``total_overs``. The scoring engine does not record DLS revised
  targets, so NRR always uses actual runs and balls.
* Abandoned, no-result, cancelled and walkover fixtures never contribute
  runs or overs, unless the forfeit policy credits the walkover winner
  with its full overs quota bowled for zero runs.
* Deductions and bonuses change points only.
* Ranking applies the versioned tie-breakers in order (points is always
  first). A tie that the configured breakers cannot separate stays
  unresolved until an organizer records an adjudicated placement with a
  reason; the adjudication is void automatically if the tied rows change.
"""

from __future__ import annotations
from collections import defaultdict
from fractions import Fraction
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.tournament_rules import TournamentRules
from app.models import (
    Innings,
    Team,
    Tournament,
    TournamentGroup,
    TournamentRuleSet,
    TournamentStatus,
    TournamentTeam,
)
from app.models.entities.tournaments import TournamentPointDeduction
from app.repositories.tournaments import TournamentRepository
from app.services.tournament_decisions import latest_by_key, list_decisions, record_decision
from app.services.tournament_results import (
    LEAGUE_STAGES,
    OfficialOutcome,
    fixture_outcomes,
    published_fixtures,
)
from app.services.tournaments import locked_tournament, tournament_audit, tournament_transaction


ADJUDICATION_SET = "standings_adjudication"
ADJUDICATION_CLEAR = "standings_adjudication_revoked"
BONUS_SET = "points_bonus"
BONUS_CLEAR = "points_bonus_revoked"
LEAGUE_KEY = "league"

CONVENTIONS = {
    "net_run_rate": "(runs scored / overs faced) - (runs conceded / overs bowled); overs = legal balls / balls per over",
    "all_out": "full_quota: a side bowled out is charged the match overs quota; overs_faced: actual overs",
    "interrupted_matches": "The match's configured total_overs is the quota; DLS revised targets are not recorded, NRR uses actual scores",
    "excluded_from_nrr": "abandoned, no-result, cancelled and walkover fixtures",
    "deductions_and_bonuses": "points only",
    "unresolved_ties": "remain unresolved until an organizer records an adjudicated placement with a reason",
}


async def get_standings_rules(session: AsyncSession, tournament_id: UUID) -> tuple[TournamentRuleSet, TournamentRules]:
    version = await session.scalar(
        select(TournamentRuleSet)
        .where(TournamentRuleSet.tournament_id == tournament_id)
        .order_by(TournamentRuleSet.version.desc())
        .limit(1)
    )

    if version is None:
        raise ConflictError("Tournament rules are not configured")

    return version, TournamentRules.model_validate(version.rules)


def overs_notation(balls: int, balls_per_over: int = 6) -> str:
    return f"{balls // balls_per_over}.{balls % balls_per_over}"


def new_standing(team: dict) -> dict:
    return {
        "membership_id": team.get("membership_id"),
        "team_id": team["team_id"],
        "team_name": team.get("team_name"),
        "group_key": team.get("group_key") or LEAGUE_KEY,
        "group_name": team.get("group_name") or "League",
        "played": 0,
        "won": 0,
        "lost": 0,
        "tied": 0,
        "drawn": 0,
        "no_result": 0,
        "abandoned": 0,
        "forfeited": 0,
        "walkover_wins": 0,
        "points": 0,
        "deductions": 0,
        "bonus_points": 0,
        "runs_for": 0,
        "runs_against": 0,
        "balls_faced": 0,
        "balls_bowled": 0,
        "wickets_taken": 0,
        "wickets_lost": 0,
        "overs_faced": Fraction(0),
        "overs_bowled": Fraction(0),
        "net_run_rate": Fraction(0),
        "form": [],
    }


def apply_outcome(outcome: OfficialOutcome, home: dict, away: dict, rules: TournamentRules) -> None:
    """Apply points and W/L/T counts for one final outcome."""

    points = rules.points
    policy = rules.standings_policy

    if outcome.outcome == "excluded":
        return

    home["played"] += 1
    away["played"] += 1

    if outcome.outcome in {"win", "forfeit"}:
        winner, loser = (home, away) if outcome.winner_team_id == home["team_id"] else (away, home)

        if outcome.winner_team_id != winner["team_id"]:
            raise ConflictError("Official winner is not a fixture team")

        winner["points"] += points.win

        if outcome.outcome == "forfeit":
            winner["walkover_wins"] += 1
            loser["forfeited"] += 1
            loser["points"] += points.forfeit

            if policy.forfeit_counts_as_win:
                winner["won"] += 1
                loser["lost"] += 1

            winner["form"].append("W")
            loser["form"].append("L")
            return

        winner["won"] += 1
        loser["lost"] += 1
        loser["points"] += points.loss
        winner["form"].append("W")
        loser["form"].append("L")
        return

    if outcome.outcome == "tie":
        for row in (home, away):
            row["tied"] += 1
            row["points"] += points.tie
            row["form"].append("T")
        return

    if outcome.outcome == "no_result":
        for row in (home, away):
            row["no_result"] += 1
            row["points"] += points.no_result
            row["form"].append("N")
        return

    if outcome.outcome == "abandoned":
        for row in (home, away):
            row["abandoned"] += 1
            row["form"].append("A")

            if policy.abandoned_match_points == "no_result":
                row["points"] += points.no_result
        return

    raise ConflictError(f"Unsupported official outcome: {outcome.outcome}")


def quota_balls(result: dict) -> int | None:
    if result.get("total_overs"):
        return result["total_overs"] * result["balls_per_over"]
    return None


def apply_innings(innings: dict, result: dict, standings: dict, rules: TournamentRules) -> None:
    batting = standings[innings["batting_team_id"]]
    bowling = standings[innings["bowling_team_id"]]
    balls_per_over = result["balls_per_over"]
    side_size = innings.get("batting_side_size") or result["players_per_side"]
    balls = innings["legal_balls"]
    all_out = innings["wickets"] >= side_size - 1
    quota = quota_balls(result)

    if all_out and quota and rules.standings_policy.all_out_net_run_rate_overs == "full_quota":
        balls = max(balls, quota)

    overs = Fraction(balls, balls_per_over)

    batting["runs_for"] += innings["total_runs"]
    batting["balls_faced"] += balls
    batting["overs_faced"] += overs
    batting["wickets_lost"] += innings["wickets"]

    bowling["runs_against"] += innings["total_runs"]
    bowling["balls_bowled"] += balls
    bowling["overs_bowled"] += overs
    bowling["wickets_taken"] += innings["wickets"]


def apply_forfeit_net_run_rate(outcome: OfficialOutcome, result: dict, standings: dict, rules: TournamentRules) -> None:
    if rules.standings_policy.forfeit_net_run_rate != "winner_credited_full_overs":
        return

    quota = quota_balls(result) or rules.overs_per_innings * result["balls_per_over"]
    winner = standings[outcome.winner_team_id]
    winner["balls_bowled"] += quota
    winner["overs_bowled"] += Fraction(quota, result["balls_per_over"])


def calculate_nrr(row: dict) -> Fraction:
    scored = Fraction(row["runs_for"]) / row["overs_faced"] if row["overs_faced"] else Fraction(0)
    conceded = Fraction(row["runs_against"]) / row["overs_bowled"] if row["overs_bowled"] else Fraction(0)
    return scored - conceded


def effective_tie_breakers(rules: TournamentRules) -> list[str]:
    breakers = list(rules.tie_breakers)
    return breakers if breakers and breakers[0] == "points" else ["points", *[b for b in breakers if b != "points"]]


def adjudication_signature(rows: list[dict]) -> list[list]:
    return sorted(
        [str(row["team_id"]), row["points"], row["won"], str(Fraction(row["net_run_rate"]))]
        for row in rows
    )


def rank_standings(
    rows: list[dict],
    rules: TournamentRules,
    head_to_head: dict,
    adjudication: dict | None = None,
) -> list[dict]:
    breakers = effective_tie_breakers(rules)

    def metric(row, breaker, tied_ids):
        if breaker == "points":
            return row["points"]
        if breaker == "wins":
            return row["won"]
        if breaker == "net_run_rate":
            return row["net_run_rate"]
        if breaker == "wickets":
            if rules.standings_policy.wickets_metric == "fewest_wickets_lost":
                return -row["wickets_lost"]
            return row["wickets_taken"]
        if breaker == "head_to_head":
            return sum(
                head_to_head.get((row["team_id"], opponent), 0)
                for opponent in tied_ids
                if opponent != row["team_id"]
            )
        return 0

    def resolve(group, index):
        if len(group) <= 1 or index >= len(breakers):
            return [group]

        breaker = breakers[index]

        if breaker == "drawing_of_lots":
            # A drawing of lots is an official act, never a UUID sort.
            return [group]

        tied_ids = {row["team_id"] for row in group}
        buckets = defaultdict(list)

        for row in group:
            buckets[metric(row, breaker, tied_ids)].append(row)

        resolved = []
        for value in sorted(buckets, reverse=True):
            resolved.extend(resolve(buckets[value], index + 1))
        return resolved

    result = []
    position = 1

    for bucket in resolve(rows, 0):
        ordered = sorted(bucket, key=lambda item: (str(item["team_name"] or ""), str(item["team_id"])))
        adjudicated = False

        if len(bucket) > 1 and adjudication:
            bucket_ids = {str(row["team_id"]) for row in bucket}
            order = [str(team_id) for team_id in adjudication.get("team_ids", [])]

            if (
                set(order) == bucket_ids
                and adjudication.get("signature") == adjudication_signature(bucket)
            ):
                lookup = {str(row["team_id"]): row for row in bucket}
                ordered = [lookup[team_id] for team_id in order]
                adjudicated = True

        for offset, row in enumerate(ordered):
            row["rank"] = position + offset if adjudicated else position
            row["ranking_unresolved"] = len(bucket) > 1 and not adjudicated
            row["adjudicated"] = adjudicated

            if adjudicated:
                row["adjudication"] = {
                    "decision_id": adjudication.get("decision_id"),
                    "reason": adjudication.get("reason"),
                }

            result.append(row)

        position += len(bucket)

    return result


def serialize_row(row: dict, balls_per_over: int) -> dict:
    nrr = row["net_run_rate"]
    return {
        **{key: value for key, value in row.items() if key not in {"overs_faced", "overs_bowled", "net_run_rate"}},
        "overs_faced": overs_notation(row["balls_faced"], balls_per_over),
        "overs_bowled": overs_notation(row["balls_bowled"], balls_per_over),
        "overs_faced_decimal": round(float(row["overs_faced"]), 6),
        "overs_bowled_decimal": round(float(row["overs_bowled"]), 6),
        "net_run_rate": round(float(nrr), 3),
        "net_run_rate_exact": str(nrr),
        "form": row["form"][-5:],
    }


def compute_standings(
    *,
    teams: list[dict],
    results: list[dict],
    rules: TournamentRules,
    adjustments: list[dict] = (),
    adjudications: dict | None = None,
) -> dict:
    """Pure points-table computation.

    ``results`` items: fixture_id, home_team_id, away_team_id, outcome
    (``OfficialOutcome``), innings (list of dicts), total_overs,
    balls_per_over, players_per_side. Items must already be in
    chronological order.
    """

    adjudications = adjudications or {}
    standings = {team["team_id"]: new_standing(team) for team in teams}
    head_to_head = defaultdict(int)
    pending, disputed, warnings = [], [], []

    for result in results:
        outcome: OfficialOutcome = result["outcome"]
        home_id, away_id = result["home_team_id"], result["away_team_id"]

        if outcome.outcome == "disputed":
            disputed.append(str(result["fixture_id"]))
            continue

        if not outcome.is_final:
            pending.append(str(result["fixture_id"]))
            continue

        if home_id not in standings or away_id not in standings:
            warnings.append(
                f"Fixture {result['fixture_id']} involves a team that is not an approved entrant; excluded"
            )
            continue

        home, away = standings[home_id], standings[away_id]
        before = (home["points"], away["points"])
        apply_outcome(outcome, home, away, rules)

        if outcome.outcome in {"win", "tie"} or rules.standings_policy.head_to_head_scope == "all_results":
            head_to_head[(home_id, away_id)] += home["points"] - before[0]
            head_to_head[(away_id, home_id)] += away["points"] - before[1]

        if outcome.counts_in_net_run_rate:
            for innings in result.get("innings", []):
                apply_innings(innings, result, standings, rules)
        elif outcome.outcome == "forfeit":
            apply_forfeit_net_run_rate(outcome, result, standings, rules)

    for adjustment in adjustments:
        row = standings.get(adjustment["team_id"])

        if row is None:
            continue

        if adjustment["kind"] == "deduction":
            row["deductions"] += adjustment["points"]
            row["points"] -= adjustment["points"]
        else:
            row["bonus_points"] += adjustment["points"]
            row["points"] += adjustment["points"]

    grouped = defaultdict(list)

    for row in standings.values():
        row["net_run_rate"] = calculate_nrr(row)
        grouped[(row["group_key"], row["group_name"])].append(row)

    balls_per_over = rules.balls_per_over
    tables = []

    for (group_key, group_name), rows in sorted(grouped.items(), key=lambda item: str(item[0][1])):
        ranked = rank_standings(rows, rules, head_to_head, adjudications.get(group_key))
        tables.append({
            "group_key": group_key,
            "group_id": group_key if group_key not in {LEAGUE_KEY} and not str(group_key).startswith("planner:") else None,
            "group_name": group_name,
            "standings": [serialize_row(row, balls_per_over) for row in ranked],
        })

    return {
        "tables": tables,
        "pending_fixtures": pending,
        "disputed_fixtures": disputed,
        "warnings": warnings,
        "ranking_unresolved": any(row["ranking_unresolved"] for table in tables for row in table["standings"]),
        "tie_breakers": effective_tie_breakers(rules),
        "conventions": CONVENTIONS,
    }


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------


async def standings_teams(session: AsyncSession, tournament_id: UUID, fixtures) -> list[dict]:
    memberships = (
        await session.scalars(
            select(TournamentTeam).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.registration_status == "approved",
                TournamentTeam.is_reserve.is_(False),
            )
        )
    ).all()
    team_ids = [membership.team_id for membership in memberships]
    names = dict(
        (await session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()
    ) if team_ids else {}
    groups = {
        group.id: group.name
        for group in (
            await session.scalars(select(TournamentGroup).where(TournamentGroup.tournament_id == tournament_id))
        ).all()
    }

    # Groups drawn by the fixture planner live in the published snapshot.
    planner_groups = {}
    for item in fixtures:
        if item.group_name and item.stage in LEAGUE_STAGES:
            for team_id in (item.fixture.home_team_id, item.fixture.away_team_id):
                if team_id is not None:
                    planner_groups[team_id] = item.group_name

    teams = []
    for membership in memberships:
        if membership.group_id is not None:
            group_key, group_name = str(membership.group_id), groups.get(membership.group_id, "Group")
        elif membership.team_id in planner_groups:
            group_name = planner_groups[membership.team_id]
            group_key = f"planner:{group_name}"
        else:
            group_key, group_name = LEAGUE_KEY, "League"

        teams.append({
            "membership_id": membership.id,
            "team_id": membership.team_id,
            "team_name": membership.display_name or names.get(membership.team_id),
            "group_key": group_key,
            "group_name": group_name,
        })

    return teams


async def standings_adjustments(session: AsyncSession, tournament_id: UUID, teams: list[dict]) -> list[dict]:
    by_membership = {team["membership_id"]: team["team_id"] for team in teams}
    deductions = (
        await session.scalars(
            select(TournamentPointDeduction).where(
                TournamentPointDeduction.tournament_id == tournament_id,
                TournamentPointDeduction.revoked_at.is_(None),
            )
        )
    ).all()
    adjustments = [
        {"team_id": by_membership[item.tournament_team_id], "points": item.points, "kind": "deduction"}
        for item in deductions
        if item.tournament_team_id in by_membership
    ]

    for bonus in await active_bonuses(session, tournament_id):
        adjustments.append({"team_id": UUID(bonus["team_id"]), "points": bonus["points"], "kind": "bonus"})

    return adjustments


async def active_bonuses(session: AsyncSession, tournament_id: UUID) -> list[dict]:
    decisions = await list_decisions(session, tournament_id, {BONUS_SET, BONUS_CLEAR})
    revoked = {str(item.payload.get("bonus_id")) for item in decisions if item.decision_type == BONUS_CLEAR}
    return [
        {**item.payload, "bonus_id": str(item.id), "reason": item.reason, "created_at": item.created_at}
        for item in decisions
        if item.decision_type == BONUS_SET and str(item.id) not in revoked
    ]


async def active_adjudications(session: AsyncSession, tournament_id: UUID) -> dict:
    decisions = await list_decisions(session, tournament_id, {ADJUDICATION_SET, ADJUDICATION_CLEAR})
    latest = latest_by_key(decisions, lambda item: item.payload.get("group_key"))
    return {
        key: {**item.payload, "decision_id": str(item.id), "reason": item.reason}
        for key, item in latest.items()
        if item.decision_type == ADJUDICATION_SET
    }


async def calculate_tournament_standings(session: AsyncSession, tournament_id: UUID) -> dict:
    tournament = await session.get(Tournament, tournament_id)

    if tournament is None:
        raise NotFoundError("Tournament not found")

    version, rules = await get_standings_rules(session, tournament_id)
    fixtures = await published_fixtures(session, tournament_id)
    league = [item for item in fixtures if item.stage in LEAGUE_STAGES]
    outcomes, match_map = await fixture_outcomes(session, tournament_id, league)

    counted_ids = [
        item.fixture.match_id for item in league
        if item.fixture.match_id and outcomes[item.fixture.id].counts_in_net_run_rate
    ]
    innings_map = defaultdict(list)

    if counted_ids:
        for innings in (await session.scalars(select(Innings).where(Innings.match_id.in_(counted_ids)))).all():
            innings_map[innings.match_id].append({
                "batting_team_id": innings.batting_team_id,
                "bowling_team_id": innings.bowling_team_id,
                "total_runs": innings.total_runs,
                "wickets": innings.wickets,
                "legal_balls": innings.legal_balls,
                "batting_side_size": innings.batting_side_size,
            })

    warnings = []
    results = []

    def chronology(item):
        fixture = item.fixture
        match = match_map.get(fixture.match_id)
        moment = (match.completed_at if match and match.completed_at else None) or fixture.scheduled_at
        return (moment is None, moment.isoformat() if moment else "", fixture.fixture_number)

    for item in sorted(league, key=chronology):
        fixture = item.fixture
        match = match_map.get(fixture.match_id)
        home_id, away_id = fixture.home_team_id, fixture.away_team_id

        if match is not None and outcomes[fixture.id].source == "match":
            if {home_id, away_id} != {match.team_a_id, match.team_b_id}:
                warnings.append(f"Fixture {fixture.fixture_number} teams differ from its official match; match teams used")
            home_id, away_id = match.team_a_id, match.team_b_id

        results.append({
            "fixture_id": fixture.id,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "outcome": outcomes[fixture.id],
            "innings": innings_map.get(fixture.match_id, []),
            "total_overs": match.total_overs if match else rules.overs_per_innings,
            "balls_per_over": match.balls_per_over if match else rules.balls_per_over,
            "players_per_side": match.players_per_side if match else rules.players_per_side,
        })

    if rules.dls_enabled and rules.standings_policy.dls_net_run_rate_basis == "revised_target":
        warnings.append("DLS revised targets are not recorded by the scoring engine; NRR uses actual scores")

    teams = await standings_teams(session, tournament_id, fixtures)
    computed = compute_standings(
        teams=teams,
        results=results,
        rules=rules,
        adjustments=await standings_adjustments(session, tournament_id, teams),
        adjudications=await active_adjudications(session, tournament_id),
    )
    computed["warnings"] = warnings + computed["warnings"]

    return {
        "tournament_id": tournament_id,
        "ruleset_id": version.id,
        "ruleset_version": version.version,
        "ruleset_checksum": version.checksum,
        "points_policy": rules.points.model_dump(),
        "standings_policy": rules.standings_policy.model_dump(),
        **computed,
    }


# ---------------------------------------------------------------------------
# Organizer standings decisions
# ---------------------------------------------------------------------------


async def _open_tournament(session: AsyncSession, tournament_id: UUID) -> Tournament:
    tournament = await locked_tournament(TournamentRepository(session), tournament_id)

    if tournament.status in {TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED, TournamentStatus.CANCELLED}:
        raise ConflictError("Reopen the tournament before changing official standings")

    return tournament


async def record_standings_adjudication(
    session: AsyncSession,
    tournament_id: UUID,
    group_key: str,
    ordered_team_ids: list[UUID],
    reason: str,
    *,
    method: str = "committee",
    actor_id: str | None = None,
) -> dict:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("An adjudication reason of at least 10 characters is required")

    if len(ordered_team_ids) < 2 or len(set(ordered_team_ids)) != len(ordered_team_ids):
        raise ValidationError("Provide at least two distinct tied teams in their adjudicated order")

    async with tournament_transaction(session, "Standings adjudication"):
        await _open_tournament(session, tournament_id)
        standings = await calculate_tournament_standings(session, tournament_id)
        table = next((item for item in standings["tables"] if item["group_key"] == group_key), None)

        if table is None:
            raise NotFoundError("Standings group not found")

        requested = {str(team_id) for team_id in ordered_team_ids}
        rows = [row for row in table["standings"] if str(row["team_id"]) in requested]

        if len(rows) != len(requested):
            raise ValidationError("Every adjudicated team must belong to this table")

        if len({row["rank"] for row in rows}) != 1 or not all(row["ranking_unresolved"] for row in rows):
            raise ConflictError("Only teams in one unresolved tie can be adjudicated")

        tied = [row for row in table["standings"] if row["rank"] == rows[0]["rank"]]

        if {str(row["team_id"]) for row in tied} != requested:
            raise ConflictError("The adjudication must order every team in the tie")

        signature_rows = [
            {**row, "net_run_rate": Fraction(row["net_run_rate_exact"])} for row in tied
        ]
        payload = {
            "group_key": group_key,
            "group_name": table["group_name"],
            "team_ids": [str(team_id) for team_id in ordered_team_ids],
            "signature": adjudication_signature(signature_rows),
            "method": method,
            "ruleset_version": standings["ruleset_version"],
        }
        decision = record_decision(session, tournament_id, ADJUDICATION_SET, reason, payload, actor_id=actor_id)
        tournament_audit(session, tournament_id, "standings_adjudicated", {**payload, "reason": reason}, actor_id=actor_id)
        await session.flush()
        return {"decision_id": decision.id, **payload, "reason": reason}


async def revoke_standings_adjudication(
    session: AsyncSession,
    tournament_id: UUID,
    group_key: str,
    reason: str,
    *,
    actor_id: str | None = None,
) -> dict:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A revocation reason of at least 10 characters is required")

    async with tournament_transaction(session, "Standings adjudication revocation"):
        await _open_tournament(session, tournament_id)

        if group_key not in await active_adjudications(session, tournament_id):
            raise NotFoundError("No active adjudication for this group")

        record_decision(session, tournament_id, ADJUDICATION_CLEAR, reason, {"group_key": group_key}, actor_id=actor_id)
        tournament_audit(session, tournament_id, "standings_adjudication_revoked", {"group_key": group_key, "reason": reason}, actor_id=actor_id)
        await session.flush()
        return {"group_key": group_key, "revoked": True}


async def record_points_bonus(
    session: AsyncSession,
    tournament_id: UUID,
    team_id: UUID,
    points: int,
    reason: str,
    *,
    match_id: UUID | None = None,
    actor_id: str | None = None,
) -> dict:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A bonus reason of at least 10 characters is required")

    if points < 1:
        raise ValidationError("Bonus points must be positive")

    async with tournament_transaction(session, "Points bonus"):
        await _open_tournament(session, tournament_id)
        _, rules = await get_standings_rules(session, tournament_id)

        if not rules.points.bonus_points_enabled:
            raise ConflictError("Bonus points are disabled by the competition rules")

        membership = await session.scalar(
            select(TournamentTeam.id).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.team_id == team_id,
                TournamentTeam.registration_status == "approved",
                TournamentTeam.is_reserve.is_(False),
            )
        )

        if membership is None:
            raise ValidationError("Bonus recipient must be an approved entrant")

        payload = {"team_id": str(team_id), "points": points, "match_id": str(match_id) if match_id else None}
        decision = record_decision(session, tournament_id, BONUS_SET, reason, payload, subject_id=team_id, actor_id=actor_id)
        tournament_audit(session, tournament_id, "points_bonus_recorded", {**payload, "reason": reason}, actor_id=actor_id)
        await session.flush()
        return {"bonus_id": decision.id, **payload, "reason": reason}


async def revoke_points_bonus(
    session: AsyncSession,
    tournament_id: UUID,
    bonus_id: UUID,
    reason: str,
    *,
    actor_id: str | None = None,
) -> dict:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A revocation reason of at least 10 characters is required")

    async with tournament_transaction(session, "Points bonus revocation"):
        await _open_tournament(session, tournament_id)

        if str(bonus_id) not in {item["bonus_id"] for item in await active_bonuses(session, tournament_id)}:
            raise NotFoundError("Active bonus not found")

        record_decision(session, tournament_id, BONUS_CLEAR, reason, {"bonus_id": str(bonus_id)}, actor_id=actor_id)
        tournament_audit(session, tournament_id, "points_bonus_revoked", {"bonus_id": str(bonus_id), "reason": reason}, actor_id=actor_id)
        await session.flush()
        return {"bonus_id": bonus_id, "revoked": True}
