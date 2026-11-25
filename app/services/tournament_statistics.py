"""Tournament batting, bowling, fielding, team and record statistics.

All figures are derived from official completed matches only (a
COMPLETED ``Match`` linked to a published, non-cancelled fixture) and
from authoritative scoring rows (``DeliveryStatus.RECORDED`` deliveries
and recorded retirements). Nothing here re-scores a match.

Conventions:

* Batter balls faced exclude wides; no-balls count as balls faced.
* Bowler runs conceded exclude byes and leg-byes.
* Credited bowler wickets: bowled, caught, lbw, stumped, hit wicket.
  Run outs, obstructing the field and retired out are dismissals but are
  never credited to the bowler.
* Retired out counts as a dismissal for batting average; retired hurt
  does not.
* Batting average is ``None`` with zero dismissals; economy is ``None``
  with zero legal balls; bowling average/strike rate are ``None`` with
  zero wickets. No misleading infinities or zeros.
* Fielding credits require ``Delivery.fielder_id`` (an optional scoring
  field). Dismissals without a recorded fielder are reported separately
  as ``fielder_not_recorded`` rather than guessed.
* Player participation (matches played, teams represented) comes from
  ``MatchPlayer``. A player is aggregated once by player id; team
  attribution is per match, so transfers are never double counted.
"""

from __future__ import annotations
from collections import defaultdict
from fractions import Fraction
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    BatterRetirement,
    Delivery,
    DeliveryStatus,
    Innings,
    Match,
    MatchPlayer,
    MatchStatus,
    Player,
    RetirementType,
    Team,
    Tournament,
    WicketType,
)
from app.models.entities.fixtures import Fixture, FixtureGenerationRun


BOWLER_WICKETS = frozenset({
    WicketType.BOWLED,
    WicketType.CAUGHT,
    WicketType.LBW,
    WicketType.STUMPED,
    WicketType.HIT_WICKET,
})
FIELDING_WICKETS = frozenset({WicketType.CAUGHT, WicketType.STUMPED, WicketType.RUN_OUT})

DATA_REQUIREMENTS = {
    "fielding": "Requires the optional fielder on caught, stumped and run-out deliveries; dismissals without one are reported as fielder_not_recorded.",
    "maidens": "Derived: a complete over by a single bowler conceding no bowler runs.",
    "partnerships": "Derived from striker and non-striker on every recorded delivery.",
    "recent_form": "Last five innings in chronological order of match completion.",
}
TIE_RULES = {
    "batting": ["runs desc", "strike_rate desc", "innings asc", "player_name asc", "player_id asc"],
    "bowling": ["wickets desc", "economy asc", "average asc", "player_name asc", "player_id asc"],
    "fielding": ["total_dismissals desc", "catches desc", "player_name asc", "player_id asc"],
}


def safe_rate(numerator, denominator, scale: int = 1):
    if not denominator:
        return None
    return round(float(Fraction(numerator) * scale / Fraction(denominator)), 2)


def overs_text(balls: int, balls_per_over: int) -> str:
    return f"{balls // balls_per_over}.{balls % balls_per_over}"


def none_last(value, reverse: bool = False):
    if value is None:
        return (1, 0)
    return (0, -value if reverse else value)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


async def official_completed_match_ids(session: AsyncSession, tournament_id: UUID) -> list[UUID]:
    return await official_match_ids_for(session, [tournament_id])


async def official_match_ids_for(session: AsyncSession, tournament_ids: list[UUID]) -> list[UUID]:
    if not tournament_ids:
        return []

    return list(
        (
            await session.scalars(
                select(Match.id)
                .join(Fixture, Fixture.match_id == Match.id)
                .join(FixtureGenerationRun, FixtureGenerationRun.id == Fixture.generation_run_id)
                .where(
                    Match.tournament_id.in_(tournament_ids),
                    Fixture.tournament_id == Match.tournament_id,
                    FixtureGenerationRun.status == "published",
                    Fixture.status != "cancelled",
                    Match.status == MatchStatus.COMPLETED,
                )
                .distinct()
            )
        ).all()
    )


async def load_statistics_data(session: AsyncSession, match_ids: list[UUID]) -> dict:
    empty = {"matches": [], "innings": [], "deliveries": [], "retirements": [], "match_players": [], "players": {}, "teams": {}}

    if not match_ids:
        return empty

    matches = [
        {
            "id": row.id, "tournament_id": row.tournament_id, "team_a_id": row.team_a_id, "team_b_id": row.team_b_id,
            "balls_per_over": row.balls_per_over, "total_overs": row.total_overs, "players_per_side": row.players_per_side,
            "winner_team_id": row.winner_team_id, "result_type": row.result_type, "result_margin": row.result_margin,
            "completed_at": row.completed_at, "scheduled_at": row.scheduled_at, "match_number": row.match_number,
        }
        for row in (await session.scalars(select(Match).where(Match.id.in_(match_ids)))).all()
    ]
    innings = [
        {
            "id": row.id, "match_id": row.match_id, "innings_number": row.innings_number,
            "batting_team_id": row.batting_team_id, "bowling_team_id": row.bowling_team_id,
            "total_runs": row.total_runs, "wickets": row.wickets, "legal_balls": row.legal_balls,
            "batting_side_size": row.batting_side_size,
        }
        for row in (await session.scalars(select(Innings).where(Innings.match_id.in_(match_ids)))).all()
    ]
    columns = (
        Delivery.match_id, Delivery.innings_id, Delivery.delivery_number, Delivery.over_number,
        Delivery.striker_id, Delivery.non_striker_id, Delivery.bowler_id, Delivery.batter_runs,
        Delivery.wide_runs, Delivery.no_ball_runs, Delivery.bye_runs, Delivery.leg_bye_runs,
        Delivery.total_runs, Delivery.is_legal_ball, Delivery.wicket_type, Delivery.dismissed_player_id,
        Delivery.fielder_id,
    )
    deliveries = [
        dict(row._mapping)
        for row in (
            await session.execute(
                select(*columns)
                .where(Delivery.match_id.in_(match_ids), Delivery.status == DeliveryStatus.RECORDED)
                .order_by(Delivery.match_id, Delivery.innings_id, Delivery.delivery_number)
            )
        ).all()
    ]
    retirements = [
        {"match_id": row.match_id, "innings_id": row.innings_id, "player_id": row.player_id, "retirement_type": row.retirement_type}
        for row in (
            await session.scalars(
                select(BatterRetirement).where(
                    BatterRetirement.match_id.in_(match_ids),
                    BatterRetirement.status == DeliveryStatus.RECORDED,
                )
            )
        ).all()
    ]
    match_players = [
        {"match_id": row.match_id, "team_id": row.team_id, "player_id": row.player_id}
        for row in (await session.execute(
            select(MatchPlayer.match_id, MatchPlayer.team_id, MatchPlayer.player_id).where(MatchPlayer.match_id.in_(match_ids))
        )).all()
    ]
    player_ids = {row["player_id"] for row in match_players}
    for delivery in deliveries:
        player_ids.update(
            value for value in (delivery["striker_id"], delivery["non_striker_id"], delivery["bowler_id"], delivery["fielder_id"]) if value
        )
    players = {
        row.id: {"name": row.full_name, "date_of_birth": row.date_of_birth}
        for row in (await session.execute(
            select(Player.id, Player.full_name, Player.date_of_birth).where(Player.id.in_(player_ids))
        )).all()
    } if player_ids else {}
    team_ids = {match["team_a_id"] for match in matches} | {match["team_b_id"] for match in matches}
    teams = dict((await session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()) if team_ids else {}

    return {
        "matches": matches,
        "innings": innings,
        "deliveries": deliveries,
        "retirements": retirements,
        "match_players": match_players,
        "players": players,
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# Pure computations
# ---------------------------------------------------------------------------


def _chronology(data: dict) -> dict:
    """Sort key per innings id: (match completion, innings number)."""

    matches = {match["id"]: match for match in data["matches"]}

    def key(match_id):
        match = matches.get(match_id, {})
        moment = match.get("completed_at") or match.get("scheduled_at")
        return (moment.isoformat() if moment else "", match.get("match_number") or 0, str(match_id))

    return {
        innings["id"]: (*key(innings["match_id"]), innings["innings_number"])
        for innings in data["innings"]
    }


def compute_player_statistics(
    data: dict,
    *,
    team_id: UUID | None = None,
    min_innings: int = 0,
    min_balls: int = 0,
) -> dict:
    matches = {match["id"]: match for match in data["matches"]}
    innings_map = {innings["id"]: innings for innings in data["innings"]}
    order = _chronology(data)
    names = data["players"]
    team_names = data["teams"]

    def bats_for_filter(innings_id):
        return team_id is None or innings_map.get(innings_id, {}).get("batting_team_id") == team_id

    def bowls_for_filter(innings_id):
        return team_id is None or innings_map.get(innings_id, {}).get("bowling_team_id") == team_id

    appearances = defaultdict(set)
    player_teams = defaultdict(list)
    for row in sorted(data["match_players"], key=lambda item: (matches.get(item["match_id"], {}).get("completed_at") is None, str(matches.get(item["match_id"], {}).get("completed_at")))):
        if team_id is not None and row["team_id"] != team_id:
            continue
        appearances[row["player_id"]].add(row["match_id"])
        if row["team_id"] not in player_teams[row["player_id"]]:
            player_teams[row["player_id"]].append(row["team_id"])

    batting = defaultdict(lambda: {"innings": {}, "fours": 0, "sixes": 0})
    bowling = defaultdict(lambda: {"figures": defaultdict(lambda: {"balls": 0, "runs": 0, "wickets": 0}), "overs": Fraction(0), "bpo": set()})
    fielding = defaultdict(lambda: {"catches": 0, "stumpings": 0, "run_outs": 0})
    overs = defaultdict(lambda: {"bowlers": set(), "legal": 0, "conceded": 0})
    summary = {"total_dismissals": 0, "credited_to_bowler": 0, "run_outs": 0, "retired_out": 0, "other_not_credited": 0, "fielder_not_recorded": 0}

    def batter_innings(player_id, innings_id):
        return batting[player_id]["innings"].setdefault(innings_id, {"runs": 0, "balls": 0, "out": False})

    for delivery in data["deliveries"]:
        innings_id = delivery["innings_id"]
        match = matches.get(delivery["match_id"])
        if match is None:
            continue
        balls_per_over = match["balls_per_over"]

        if bats_for_filter(innings_id):
            striker = batter_innings(delivery["striker_id"], innings_id)
            striker["runs"] += delivery["batter_runs"]
            if not delivery["wide_runs"]:
                striker["balls"] += 1
            if delivery["batter_runs"] == 4:
                batting[delivery["striker_id"]]["fours"] += 1
            if delivery["batter_runs"] == 6:
                batting[delivery["striker_id"]]["sixes"] += 1
            if delivery["non_striker_id"]:
                batter_innings(delivery["non_striker_id"], innings_id)

        conceded = delivery["total_runs"] - delivery["bye_runs"] - delivery["leg_bye_runs"]
        wicket = delivery["wicket_type"]

        if bowls_for_filter(innings_id):
            bowler = bowling[delivery["bowler_id"]]
            figure = bowler["figures"][innings_id]
            figure["runs"] += conceded
            bowler["bpo"].add(balls_per_over)
            if delivery["is_legal_ball"]:
                figure["balls"] += 1
                bowler["overs"] += Fraction(1, balls_per_over)
            over = overs[(innings_id, delivery["over_number"])]
            over["bowlers"].add(delivery["bowler_id"])
            over["legal"] += 1 if delivery["is_legal_ball"] else 0
            over["conceded"] += conceded
            over["bpo"] = balls_per_over
            if wicket in BOWLER_WICKETS:
                figure["wickets"] += 1

        if wicket is None:
            continue

        # With a team filter the summary covers dismissals the team effected.
        if bowls_for_filter(innings_id):
            summary["total_dismissals"] += 1
            if wicket in BOWLER_WICKETS:
                summary["credited_to_bowler"] += 1
            elif wicket == WicketType.RUN_OUT:
                summary["run_outs"] += 1
            else:
                summary["other_not_credited"] += 1

        if delivery["dismissed_player_id"] and bats_for_filter(innings_id):
            batter_innings(delivery["dismissed_player_id"], innings_id)["out"] = True

        if wicket in FIELDING_WICKETS and bowls_for_filter(innings_id):
            if delivery["fielder_id"] is None:
                summary["fielder_not_recorded"] += 1
            else:
                key = {WicketType.CAUGHT: "catches", WicketType.STUMPED: "stumpings", WicketType.RUN_OUT: "run_outs"}[wicket]
                fielding[delivery["fielder_id"]][key] += 1

    for retirement in data["retirements"]:
        is_out = retirement["retirement_type"] == RetirementType.OUT
        if is_out and bowls_for_filter(retirement["innings_id"]):
            summary["total_dismissals"] += 1
            summary["retired_out"] += 1
        if not bats_for_filter(retirement["innings_id"]):
            continue
        entry = batter_innings(retirement["player_id"], retirement["innings_id"])
        if is_out:
            entry["out"] = True

    maidens = defaultdict(int)
    for over in overs.values():
        if len(over["bowlers"]) == 1 and over["legal"] >= over.get("bpo", 6) and over["conceded"] == 0:
            maidens[next(iter(over["bowlers"]))] += 1

    def player_fields(player_id):
        return {
            "player_id": player_id,
            "player_name": names.get(player_id, {}).get("name", "Unknown player"),
            "teams": [{"team_id": team, "team_name": team_names.get(team)} for team in player_teams.get(player_id, [])],
            "matches": len(appearances.get(player_id, ())),
        }

    batting_rows = []
    for player_id, record in batting.items():
        innings_list = sorted(record["innings"].items(), key=lambda item: order.get(item[0], ("",)))
        if not innings_list:
            continue
        runs = sum(entry["runs"] for _, entry in innings_list)
        balls = sum(entry["balls"] for _, entry in innings_list)
        dismissals = sum(1 for _, entry in innings_list if entry["out"])
        highest = max(innings_list, key=lambda item: (item[1]["runs"], not item[1]["out"]))[1]
        batting_rows.append({
            **player_fields(player_id),
            "innings": len(innings_list),
            "not_outs": len(innings_list) - dismissals,
            "runs": runs,
            "balls": balls,
            "dismissals": dismissals,
            "average": safe_rate(runs, dismissals),
            "strike_rate": safe_rate(runs, balls, 100),
            "highest_score": highest["runs"],
            "highest_score_not_out": not highest["out"],
            "highest_score_display": f"{highest['runs']}{'' if highest['out'] else '*'}",
            "fours": record["fours"],
            "sixes": record["sixes"],
            "boundaries": record["fours"] + record["sixes"],
            "fifties": sum(1 for _, entry in innings_list if 50 <= entry["runs"] < 100),
            "hundreds": sum(1 for _, entry in innings_list if entry["runs"] >= 100),
            "ducks": sum(1 for _, entry in innings_list if entry["runs"] == 0 and entry["out"]),
            "recent_form": [
                f"{entry['runs']}{'' if entry['out'] else '*'}" for _, entry in innings_list[-5:]
            ],
            "qualifies": len(innings_list) >= min_innings,
        })

    bowling_rows = []
    for player_id, record in bowling.items():
        figures = [figure for figure in record["figures"].values()]
        if not figures:
            continue
        balls = sum(figure["balls"] for figure in figures)
        runs = sum(figure["runs"] for figure in figures)
        wickets = sum(figure["wickets"] for figure in figures)
        best = sorted(figures, key=lambda figure: (-figure["wickets"], figure["runs"]))[0]
        bpo = next(iter(record["bpo"])) if len(record["bpo"]) == 1 else None
        bowling_rows.append({
            **player_fields(player_id),
            "innings": len(figures),
            "legal_balls": balls,
            "overs": overs_text(balls, bpo) if bpo else str(round(float(record["overs"]), 2)),
            "overs_decimal": round(float(record["overs"]), 4),
            "maidens": maidens.get(player_id, 0),
            "runs_conceded": runs,
            "wickets": wickets,
            "economy": round(float(Fraction(runs) / record["overs"]), 2) if record["overs"] else None,
            "average": safe_rate(runs, wickets),
            "strike_rate": safe_rate(balls, wickets),
            "best_figures": {"wickets": best["wickets"], "runs": best["runs"]},
            "best_figures_display": f"{best['wickets']}/{best['runs']}",
            "four_wicket_hauls": sum(1 for figure in figures if figure["wickets"] == 4),
            "five_wicket_hauls": sum(1 for figure in figures if figure["wickets"] >= 5),
            "qualifies": balls >= min_balls,
        })

    fielding_rows = [
        {**player_fields(player_id), **record, "total_dismissals": sum(record.values())}
        for player_id, record in fielding.items()
    ]

    batting_rows.sort(key=lambda row: (-row["runs"], none_last(row["strike_rate"], True), row["innings"], row["player_name"], str(row["player_id"])))
    bowling_rows.sort(key=lambda row: (-row["wickets"], none_last(row["economy"]), none_last(row["average"]), row["player_name"], str(row["player_id"])))
    fielding_rows.sort(key=lambda row: (-row["total_dismissals"], -row["catches"], row["player_name"], str(row["player_id"])))

    return {
        "batting": batting_rows,
        "bowling": bowling_rows,
        "fielding": fielding_rows,
        "dismissal_summary": summary,
        "qualification": {"min_innings": min_innings, "min_balls": min_balls},
        "tie_rules": TIE_RULES,
        "data_requirements": DATA_REQUIREMENTS,
    }


def compute_partnerships(data: dict) -> list[dict]:
    matches = {match["id"]: match for match in data["matches"]}
    innings_map = {innings["id"]: innings for innings in data["innings"]}
    names = data["players"]
    by_innings = defaultdict(list)
    for delivery in data["deliveries"]:
        by_innings[delivery["innings_id"]].append(delivery)

    result = []
    for innings_id, deliveries in by_innings.items():
        current, runs, balls, wicket_number = None, 0, 0, 0
        for delivery in sorted(deliveries, key=lambda item: item["delivery_number"]):
            pair = frozenset(value for value in (delivery["striker_id"], delivery["non_striker_id"]) if value)
            if current is not None and pair != current:
                result.append((innings_id, current, runs, balls, wicket_number + 1))
                runs, balls = 0, 0
            current = pair
            runs += delivery["total_runs"]
            balls += 1 if delivery["is_legal_ball"] else 0
            if delivery["wicket_type"] is not None:
                result.append((innings_id, current, runs, balls, wicket_number + 1))
                wicket_number += 1
                current, runs, balls = None, 0, 0
        if current is not None and (runs or balls):
            result.append((innings_id, current, runs, balls, wicket_number + 1))

    rows = []
    for innings_id, pair, runs, balls, wicket in result:
        innings = innings_map.get(innings_id, {})
        players = sorted(pair, key=str)
        rows.append({
            "match_id": innings.get("match_id"),
            "innings_number": innings.get("innings_number"),
            "team_id": innings.get("batting_team_id"),
            "team_name": data["teams"].get(innings.get("batting_team_id")),
            "wicket": wicket,
            "runs": runs,
            "balls": balls,
            "players": [{"player_id": player, "player_name": names.get(player, {}).get("name")} for player in players],
            "balls_per_over": matches.get(innings.get("match_id"), {}).get("balls_per_over", 6),
        })
    rows.sort(key=lambda row: (-row["runs"], row["balls"], str(row["match_id"]), row["wicket"]))
    return rows


def _match_result(match: dict, team_id: UUID) -> str:
    if match["result_type"] == "tie":
        return "T"
    if match["winner_team_id"] == team_id:
        return "W"
    if match["winner_team_id"] is not None:
        return "L"
    return "N"


def _score(innings: dict | None, balls_per_over: int) -> str | None:
    if innings is None:
        return None
    return f"{innings['total_runs']}/{innings['wickets']} ({overs_text(innings['legal_balls'], balls_per_over)})"


def compute_team_statistics(data: dict) -> list[dict]:
    teams = data["teams"]
    innings_by_match = defaultdict(list)
    for innings in data["innings"]:
        innings_by_match[innings["match_id"]].append(innings)

    extras = defaultdict(lambda: {"wides": 0, "no_balls": 0, "byes": 0, "leg_byes": 0, "fours": 0, "sixes": 0})
    innings_map = {innings["id"]: innings for innings in data["innings"]}
    for delivery in data["deliveries"]:
        innings = innings_map.get(delivery["innings_id"])
        if innings is None:
            continue
        bowling = extras[innings["bowling_team_id"]]
        bowling["wides"] += delivery["wide_runs"]
        bowling["no_balls"] += delivery["no_ball_runs"]
        bowling["byes"] += delivery["bye_runs"]
        bowling["leg_byes"] += delivery["leg_bye_runs"]
        batting = extras[innings["batting_team_id"]]
        batting["fours"] += delivery["batter_runs"] == 4
        batting["sixes"] += delivery["batter_runs"] == 6

    stats = {}
    for match in sorted(data["matches"], key=lambda item: (str(item.get("completed_at") or ""), item.get("match_number") or 0)):
        bpo = match["balls_per_over"]
        for team_id, opponent_id in ((match["team_a_id"], match["team_b_id"]), (match["team_b_id"], match["team_a_id"])):
            row = stats.setdefault(team_id, {
                "team_id": team_id, "team_name": teams.get(team_id), "matches": 0, "won": 0, "lost": 0, "tied": 0, "no_result": 0,
                "runs_scored": 0, "balls_faced": 0, "wickets_lost": 0, "runs_conceded": 0, "balls_bowled": 0, "wickets_taken": 0,
                "overs_faced": Fraction(0), "overs_bowled": Fraction(0),
                "highest_total": None, "lowest_total": None, "form": [],
            })
            result = _match_result(match, team_id)
            row["matches"] += 1
            row[{"W": "won", "L": "lost", "T": "tied", "N": "no_result"}[result]] += 1
            own = next((item for item in innings_by_match[match["id"]] if item["batting_team_id"] == team_id), None)
            other = next((item for item in innings_by_match[match["id"]] if item["batting_team_id"] == opponent_id), None)
            for innings in innings_by_match[match["id"]]:
                if innings["batting_team_id"] == team_id:
                    row["runs_scored"] += innings["total_runs"]
                    row["balls_faced"] += innings["legal_balls"]
                    row["overs_faced"] += Fraction(innings["legal_balls"], bpo)
                    row["wickets_lost"] += innings["wickets"]
                    if row["highest_total"] is None or innings["total_runs"] > row["highest_total"]:
                        row["highest_total"] = innings["total_runs"]
                    if row["lowest_total"] is None or innings["total_runs"] < row["lowest_total"]:
                        row["lowest_total"] = innings["total_runs"]
                else:
                    row["runs_conceded"] += innings["total_runs"]
                    row["balls_bowled"] += innings["legal_balls"]
                    row["overs_bowled"] += Fraction(innings["legal_balls"], bpo)
                    row["wickets_taken"] += innings["wickets"]
            row["form"].append({
                "match_id": match["id"],
                "opponent_id": opponent_id,
                "opponent_name": teams.get(opponent_id),
                "result": result,
                "score_for": _score(own, bpo),
                "score_against": _score(other, bpo),
                "margin": match["result_margin"],
                "result_type": match["result_type"],
                "scorecard_url": f"/scorecard/{match['id']}",
            })

    rows = []
    for team_id, row in stats.items():
        overs_faced, overs_bowled = row.pop("overs_faced"), row.pop("overs_bowled")
        rows.append({
            **row,
            **extras.get(team_id, {"wides": 0, "no_balls": 0, "byes": 0, "leg_byes": 0, "fours": 0, "sixes": 0}),
            "extras_conceded": sum(extras[team_id][key] for key in ("wides", "no_balls", "byes", "leg_byes")) if team_id in extras else 0,
            "run_rate": round(float(Fraction(row["runs_scored"]) / overs_faced), 2) if overs_faced else None,
            "economy": round(float(Fraction(row["runs_conceded"]) / overs_bowled), 2) if overs_bowled else None,
            "batting_average": safe_rate(row["runs_scored"], row["wickets_lost"]),
            "bowling_average": safe_rate(row["runs_conceded"], row["wickets_taken"]),
        })
    rows.sort(key=lambda row: (-row["won"], -row["runs_scored"], str(row["team_name"] or ""), str(row["team_id"])))
    return rows


def compute_records(data: dict, limit: int = 5) -> dict:
    teams = data["teams"]
    matches = {match["id"]: match for match in data["matches"]}
    innings_by_match = defaultdict(list)
    for innings in data["innings"]:
        innings_by_match[innings["match_id"]].append(innings)

    def innings_row(innings):
        match = matches[innings["match_id"]]
        bpo = match["balls_per_over"]
        return {
            "match_id": innings["match_id"],
            "team_id": innings["batting_team_id"],
            "team_name": teams.get(innings["batting_team_id"]),
            "opponent_id": innings["bowling_team_id"],
            "opponent_name": teams.get(innings["bowling_team_id"]),
            "runs": innings["total_runs"],
            "wickets": innings["wickets"],
            "overs": overs_text(innings["legal_balls"], bpo),
            "score": _score(innings, bpo),
            "scorecard_url": f"/scorecard/{innings['match_id']}",
        }

    def completed_innings(innings):
        match = matches[innings["match_id"]]
        side = innings.get("batting_side_size") or match["players_per_side"]
        quota = (match["total_overs"] or 0) * match["balls_per_over"]
        return innings["wickets"] >= side - 1 or (quota and innings["legal_balls"] >= quota)

    all_innings = [innings for innings in data["innings"] if innings["match_id"] in matches]
    highest = sorted(all_innings, key=lambda item: (-item["total_runs"], item["wickets"], str(item["id"])))
    lowest = sorted([item for item in all_innings if completed_innings(item)], key=lambda item: (item["total_runs"], str(item["id"])))

    players = compute_player_statistics(data)
    individual = []
    innings_scores = defaultdict(lambda: {"runs": 0, "balls": 0, "out": False})
    innings_map = {innings["id"]: innings for innings in data["innings"]}
    for delivery in data["deliveries"]:
        entry = innings_scores[(delivery["innings_id"], delivery["striker_id"])]
        entry["runs"] += delivery["batter_runs"]
        entry["balls"] += 0 if delivery["wide_runs"] else 1
        if delivery["dismissed_player_id"]:
            innings_scores[(delivery["innings_id"], delivery["dismissed_player_id"])]["out"] = True
    for retirement in data["retirements"]:
        if retirement["retirement_type"] == RetirementType.OUT:
            innings_scores[(retirement["innings_id"], retirement["player_id"])]["out"] = True
    for (innings_id, player_id), entry in innings_scores.items():
        innings = innings_map.get(innings_id)
        if innings is None:
            continue
        individual.append({
            "player_id": player_id,
            "player_name": data["players"].get(player_id, {}).get("name"),
            "team_name": teams.get(innings["batting_team_id"]),
            "opponent_name": teams.get(innings["bowling_team_id"]),
            "match_id": innings["match_id"],
            "runs": entry["runs"],
            "balls": entry["balls"],
            "not_out": not entry["out"],
            "display": f"{entry['runs']}{'' if entry['out'] else '*'} ({entry['balls']})",
        })
    individual.sort(key=lambda row: (-row["runs"], row["balls"], str(row["player_id"]), str(row["match_id"])))

    figures = defaultdict(lambda: {"wickets": 0, "runs": 0, "balls": 0})
    for delivery in data["deliveries"]:
        innings = innings_map.get(delivery["innings_id"])
        if innings is None:
            continue
        figure = figures[(delivery["innings_id"], delivery["bowler_id"])]
        figure["runs"] += delivery["total_runs"] - delivery["bye_runs"] - delivery["leg_bye_runs"]
        figure["balls"] += 1 if delivery["is_legal_ball"] else 0
        figure["wickets"] += 1 if delivery["wicket_type"] in BOWLER_WICKETS else 0
    best_bowling = sorted(
        [
            {
                "player_id": player_id,
                "player_name": data["players"].get(player_id, {}).get("name"),
                "team_name": teams.get(innings_map[innings_id]["bowling_team_id"]),
                "opponent_name": teams.get(innings_map[innings_id]["batting_team_id"]),
                "match_id": innings_map[innings_id]["match_id"],
                **figure,
                "display": f"{figure['wickets']}/{figure['runs']}",
            }
            for (innings_id, player_id), figure in figures.items()
        ],
        key=lambda row: (-row["wickets"], row["runs"], row["balls"], str(row["player_id"])),
    )

    chases, wins_by_runs, wins_by_wickets = [], [], []
    for match in matches.values():
        ordered = sorted(innings_by_match[match["id"]], key=lambda item: item["innings_number"])
        if match["result_type"] == "wickets" and len(ordered) >= 2:
            chasing = ordered[-1]
            target = sum(item["total_runs"] for item in ordered if item["batting_team_id"] != chasing["batting_team_id"]) - sum(
                item["total_runs"] for item in ordered[:-1] if item["batting_team_id"] == chasing["batting_team_id"]) + 1
            quota = (match["total_overs"] or 0) * match["balls_per_over"]
            row = {**innings_row(chasing), "target": target, "margin_wickets": match["result_margin"],
                   "balls_remaining": max(quota - chasing["legal_balls"], 0) if quota else None}
            chases.append(row)
            wins_by_wickets.append(row)
        if match["result_type"] == "runs":
            wins_by_runs.append({
                "match_id": match["id"],
                "winner_id": match["winner_team_id"],
                "winner_name": teams.get(match["winner_team_id"]),
                "margin_runs": match["result_margin"],
                "scorecard_url": f"/scorecard/{match['id']}",
            })

    return {
        "highest_totals": [innings_row(item) for item in highest[:limit]],
        "lowest_completed_totals": [innings_row(item) for item in lowest[:limit]],
        "highest_individual_scores": individual[:limit],
        "best_bowling_figures": best_bowling[:limit],
        "top_partnerships": compute_partnerships(data)[:limit],
        "successful_chases": sorted(chases, key=lambda row: (-row["target"], str(row["match_id"])))[:limit],
        "biggest_wins_by_runs": sorted(wins_by_runs, key=lambda row: (-(row["margin_runs"] or 0), str(row["match_id"])))[:limit],
        "biggest_wins_by_wickets": sorted(
            wins_by_wickets, key=lambda row: (-(row["margin_wickets"] or 0), -(row["balls_remaining"] or 0), str(row["match_id"]))
        )[:limit],
        "most_sixes": sorted(players["batting"], key=lambda row: (-row["sixes"], -row["runs"], str(row["player_id"])))[:limit],
        "data_requirements": DATA_REQUIREMENTS,
    }


def compute_player_profile(data: dict, player_id: UUID) -> dict:
    stats = compute_player_statistics(data)
    matches = {match["id"]: match for match in data["matches"]}
    innings_map = {innings["id"]: innings for innings in data["innings"]}
    team_of = {(row["match_id"], row["player_id"]): row["team_id"] for row in data["match_players"]}
    per_match = defaultdict(lambda: {"batting": None, "bowling": None, "catches": 0, "stumpings": 0, "run_outs": 0})

    for delivery in data["deliveries"]:
        innings = innings_map.get(delivery["innings_id"])
        if innings is None:
            continue
        entry = per_match[delivery["match_id"]]
        if player_id in (delivery["striker_id"], delivery["non_striker_id"]):
            entry["batting"] = entry["batting"] or {"runs": 0, "balls": 0, "out": False}
        if delivery["striker_id"] == player_id:
            entry["batting"]["runs"] += delivery["batter_runs"]
            entry["batting"]["balls"] += 0 if delivery["wide_runs"] else 1
        if delivery["dismissed_player_id"] == player_id:
            entry["batting"] = entry["batting"] or {"runs": 0, "balls": 0, "out": False}
            entry["batting"]["out"] = True
        if delivery["bowler_id"] == player_id:
            entry["bowling"] = entry["bowling"] or {"balls": 0, "runs": 0, "wickets": 0}
            entry["bowling"]["runs"] += delivery["total_runs"] - delivery["bye_runs"] - delivery["leg_bye_runs"]
            entry["bowling"]["balls"] += 1 if delivery["is_legal_ball"] else 0
            entry["bowling"]["wickets"] += 1 if delivery["wicket_type"] in BOWLER_WICKETS else 0
        if delivery["fielder_id"] == player_id and delivery["wicket_type"] in FIELDING_WICKETS:
            key = {WicketType.CAUGHT: "catches", WicketType.STUMPED: "stumpings", WicketType.RUN_OUT: "run_outs"}[delivery["wicket_type"]]
            entry[key] += 1

    played = {row["match_id"] for row in data["match_players"] if row["player_id"] == player_id}
    match_rows = []
    for match_id in sorted(played | set(per_match), key=lambda item: (str(matches.get(item, {}).get("completed_at") or ""), str(item))):
        match = matches.get(match_id)
        if match is None:
            continue
        team_id = team_of.get((match_id, player_id))
        opponent = match["team_b_id"] if team_id == match["team_a_id"] else match["team_a_id"]
        entry = per_match.get(match_id, {"batting": None, "bowling": None, "catches": 0, "stumpings": 0, "run_outs": 0})
        bpo = match["balls_per_over"]
        match_rows.append({
            "match_id": match_id,
            "team_id": team_id,
            "team_name": data["teams"].get(team_id),
            "opponent_name": data["teams"].get(opponent),
            "result": _match_result(match, team_id) if team_id else None,
            "batting": (
                f"{entry['batting']['runs']}{'' if entry['batting']['out'] else '*'} ({entry['batting']['balls']})"
                if entry["batting"] else None
            ),
            "bowling": (
                f"{entry['bowling']['wickets']}/{entry['bowling']['runs']} ({overs_text(entry['bowling']['balls'], bpo)})"
                if entry["bowling"] else None
            ),
            "catches": entry["catches"],
            "stumpings": entry["stumpings"],
            "run_outs": entry["run_outs"],
            "scorecard_url": f"/scorecard/{match_id}",
        })

    def find(rows):
        return next((row for row in rows if row["player_id"] == player_id), None)

    return {
        "player_id": player_id,
        "player_name": data["players"].get(player_id, {}).get("name"),
        "batting": find(stats["batting"]),
        "bowling": find(stats["bowling"]),
        "fielding": find(stats["fielding"]),
        "matches": match_rows,
        "data_requirements": DATA_REQUIREMENTS,
    }


# ---------------------------------------------------------------------------
# Async entry points
# ---------------------------------------------------------------------------


async def tournament_statistics_data(session: AsyncSession, tournament_id: UUID) -> dict:
    return await load_statistics_data(session, await official_completed_match_ids(session, tournament_id))


async def tournament_player_statistics(
    session: AsyncSession,
    tournament_id: UUID,
    *,
    team_id: UUID | None = None,
    min_innings: int = 0,
    min_balls: int = 0,
) -> dict:
    data = await tournament_statistics_data(session, tournament_id)
    return compute_player_statistics(data, team_id=team_id, min_innings=min_innings, min_balls=min_balls)


async def tournament_team_records(session: AsyncSession, tournament_id: UUID) -> list[dict]:
    return compute_team_statistics(await tournament_statistics_data(session, tournament_id))


async def tournament_records(session: AsyncSession, tournament_id: UUID, limit: int = 5) -> dict:
    return compute_records(await tournament_statistics_data(session, tournament_id), limit)


async def tournament_player_profile(session: AsyncSession, tournament_id: UUID, player_id: UUID) -> dict:
    return compute_player_profile(await tournament_statistics_data(session, tournament_id), player_id)


async def series_tournament_ids(session: AsyncSession, series_id: UUID, season: str | None = None) -> list[UUID]:
    statement = select(Tournament.id).where(Tournament.series_id == series_id)
    if season:
        statement = statement.where(Tournament.season == season)
    return list((await session.scalars(statement)).all())


async def series_player_statistics(
    session: AsyncSession,
    series_id: UUID,
    *,
    season: str | None = None,
    min_innings: int = 0,
    min_balls: int = 0,
) -> dict:
    """Cross-edition leaderboards; each player is aggregated exactly once."""

    tournament_ids = await series_tournament_ids(session, series_id, season)
    data = await load_statistics_data(session, await official_match_ids_for(session, tournament_ids))
    return {
        "series_id": series_id,
        "season": season,
        "tournament_ids": tournament_ids,
        **compute_player_statistics(data, min_innings=min_innings, min_balls=min_balls),
    }
