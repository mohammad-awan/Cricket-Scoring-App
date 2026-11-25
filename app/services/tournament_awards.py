"""Computed award candidate rankings.

These rankings are *evidence only*. No algorithm selects a final
honorary award: an organizer must confirm every award (see
``tournament_award_management``), and manual/organizer-selected awards
are always recorded separately from computed candidates.
"""

from __future__ import annotations
from datetime import date
from fractions import Fraction
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError
from app.models import Tournament
from app.models.entities.tournament_operations import TournamentAward
from app.schemas.tournament_awards import AwardSettings, AwardWeights, EmergingEligibility
from app.services.tournament_decisions import list_decisions
from app.services.tournament_statistics import compute_player_statistics, tournament_statistics_data


SETTINGS_DECISION = "award_settings"
VOTE_DECISION = "award_vote"
PLAYER_OF_MATCH_PREFIX = "player_of_match:"

COMPUTED_AWARDS = {
    "batter_of_tournament": "Batter of the Tournament",
    "bowler_of_tournament": "Bowler of the Tournament",
    "player_of_tournament": "Player of the Tournament",
    "emerging_player": "Emerging Player",
    "best_fielder": "Best Fielder",
    "most_sixes": "Most Sixes",
    "best_economy": "Best Economy",
}
def age_on(birth: date, reference: date) -> int:
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def emerging_eligibility(birth: date | None, rules: EmergingEligibility, reference: date) -> tuple[bool, str]:
    if not rules.configured:
        return False, "Emerging player eligibility is not configured"
    if birth is None:
        return False, "Date of birth not recorded"
    if rules.born_on_or_after and birth < rules.born_on_or_after:
        return False, f"Born before {rules.born_on_or_after.isoformat()}"
    if rules.max_age is not None and age_on(birth, rules.reference_date or reference) > rules.max_age:
        return False, f"Older than {rules.max_age} on the reference date"
    return True, "Eligible"


def player_of_tournament_scores(stats: dict, weights: AwardWeights) -> list[dict]:
    """Normalized weighted score; every component is shown for transparency."""

    players: dict = {}

    def entry(row):
        return players.setdefault(row["player_id"], {
            "player_id": row["player_id"], "player_name": row["player_name"], "teams": row.get("teams", []),
            "matches": row.get("matches", 0), "runs": 0, "batting_balls": 0, "strike_rate": None,
            "wickets": 0, "bowling_balls": 0, "economy": None, "fielding_dismissals": 0,
        })

    for row in stats["batting"]:
        player = entry(row)
        player.update(runs=row["runs"], batting_balls=row["balls"], strike_rate=row["strike_rate"])
    for row in stats["bowling"]:
        player = entry(row)
        player.update(wickets=row["wickets"], bowling_balls=row["legal_balls"], economy=row["economy"])
    for row in stats["fielding"]:
        entry(row)["fielding_dismissals"] = row["total_dismissals"]

    eligible = [player for player in players.values() if player["matches"] >= weights.minimum_matches]
    sr_pool = [p["strike_rate"] for p in eligible if p["strike_rate"] is not None and p["batting_balls"] >= weights.min_batting_balls]
    econ_pool = [p["economy"] for p in eligible if p["economy"] is not None and p["bowling_balls"] >= weights.min_bowling_balls]
    max_runs = max((p["runs"] for p in eligible), default=0)
    max_wickets = max((p["wickets"] for p in eligible), default=0)
    max_fielding = max((p["fielding_dismissals"] for p in eligible), default=0)
    max_sr = max(sr_pool, default=0)
    best_econ, worst_econ = min(econ_pool, default=None), max(econ_pool, default=None)

    def ratio(value, maximum):
        return float(Fraction(value) / Fraction(maximum)) if maximum else 0.0

    result = []
    for player in eligible:
        batting_ok = player["strike_rate"] is not None and player["batting_balls"] >= weights.min_batting_balls
        bowling_ok = player["economy"] is not None and player["bowling_balls"] >= weights.min_bowling_balls
        if bowling_ok:
            economy_norm = 1.0 if worst_econ == best_econ else (worst_econ - player["economy"]) / (worst_econ - best_econ)
        else:
            economy_norm = 0.0
        components = {
            "runs": round(ratio(player["runs"], max_runs), 4),
            "batting_efficiency": round(player["strike_rate"] / max_sr, 4) if batting_ok and max_sr else 0.0,
            "wickets": round(ratio(player["wickets"], max_wickets), 4),
            "economy": round(economy_norm, 4),
            "fielding": round(ratio(player["fielding_dismissals"], max_fielding), 4),
        }
        score = sum(components[key] * getattr(weights, key) for key in components)
        result.append({**player, "components": components, "award_score": round(score, 4)})

    result.sort(key=lambda row: (-row["award_score"], -row["runs"], -row["wickets"], row["player_name"], str(row["player_id"])))
    return result


def _leader_flag(rows: list[dict], metric) -> bool:
    if not rows:
        return False
    return len(rows) == 1 or metric(rows[0]) != metric(rows[1])


def compute_award_candidates(stats: dict, settings: AwardSettings, births: dict, reference: date, pom_counts: dict) -> dict:
    limit = settings.candidates_limit
    batting = [row for row in stats["batting"] if row["innings"] >= settings.batting_min_innings]
    bowling = stats["bowling"]
    fielding = stats["fielding"]
    scores = player_of_tournament_scores(stats, settings.weights)

    emerging_rows, excluded = [], []
    for row in scores:
        eligible, reason = emerging_eligibility(births.get(row["player_id"]), settings.emerging, reference)
        if eligible:
            emerging_rows.append(row)
        else:
            excluded.append({"player_id": row["player_id"], "player_name": row["player_name"], "reason": reason})

    sixes = sorted(batting, key=lambda row: (-row["sixes"], -row["runs"], row["player_name"], str(row["player_id"])))
    economy = sorted(
        [row for row in bowling if row["economy"] is not None and row["legal_balls"] >= settings.min_economy_balls],
        key=lambda row: (row["economy"], -row["wickets"], row["player_name"], str(row["player_id"])),
    )

    def award(code, rows, basis, metric, **extra):
        return {
            "award_code": code,
            "title": COMPUTED_AWARDS[code],
            "computed": True,
            "basis": basis,
            "status": "provisional_candidates",
            "leader_unambiguous": _leader_flag(rows, metric),
            "candidates": rows[:limit],
            **extra,
        }

    awards = [
        award("batter_of_tournament", batting, "Most runs; ties by strike rate, then fewer innings",
              lambda row: (row["runs"], row["strike_rate"]), minimum_innings=settings.batting_min_innings),
        award("bowler_of_tournament", bowling, "Most credited wickets; ties by economy, then average",
              lambda row: (row["wickets"], row["economy"], row["average"])),
        award("player_of_tournament", scores, "Normalized weighted score of runs, strike rate, wickets, economy and fielding",
              lambda row: row["award_score"], weights=settings.weights.model_dump()),
        award("emerging_player", emerging_rows, "Player of the Tournament score among eligible players",
              lambda row: row["award_score"], eligibility=settings.emerging.model_dump(mode="json"),
              eligibility_configured=settings.emerging.configured, excluded_count=len(excluded), excluded=excluded[:limit]),
        award("best_fielder", fielding, "Most catches, stumpings and run outs with a recorded fielder",
              lambda row: (row["total_dismissals"], row["catches"]), data_requirement="Requires the optional fielder on dismissals"),
        award("most_sixes", sixes, "Most sixes; ties by runs", lambda row: (row["sixes"], row["runs"])),
        award("best_economy", economy, f"Lowest economy with at least {settings.min_economy_balls} legal balls; ties by wickets",
              lambda row: (row["economy"], row["wickets"]), minimum_legal_balls=settings.min_economy_balls),
    ]

    names = {row["player_id"]: row["player_name"] for row in scores}
    pom = sorted(
        [{"player_id": player_id, "player_name": names.get(player_id), "awards": count} for player_id, count in pom_counts.items()],
        key=lambda row: (-row["awards"], str(row["player_name"] or ""), str(row["player_id"])),
    )

    return {
        "status": "provisional_candidates",
        "note": "Computed candidates are evidence only. Every award must be confirmed by an organizer.",
        "awards": awards,
        "player_of_match_aggregates": pom,
        "settings": settings.model_dump(mode="json"),
    }


async def get_award_settings(session: AsyncSession, tournament_id: UUID) -> AwardSettings:
    decisions = await list_decisions(session, tournament_id, {SETTINGS_DECISION})
    if not decisions:
        return AwardSettings()
    return AwardSettings.model_validate(decisions[-1].payload)


async def player_of_match_counts(session: AsyncSession, tournament_id: UUID) -> dict:
    awards = (
        await session.scalars(
            select(TournamentAward).where(
                TournamentAward.tournament_id == tournament_id,
                TournamentAward.status == "confirmed",
                TournamentAward.award_code.like(f"{PLAYER_OF_MATCH_PREFIX}%"),
            )
        )
    ).all()
    counts: dict = {}
    for award in awards:
        counts[award.player_id] = counts.get(award.player_id, 0) + 1
    return counts


async def tournament_award_candidates(
    session: AsyncSession,
    tournament_id: UUID,
    settings: AwardSettings | None = None,
) -> dict:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    settings = settings or await get_award_settings(session, tournament_id)
    data = await tournament_statistics_data(session, tournament_id)
    stats = compute_player_statistics(data)
    births = {player_id: info.get("date_of_birth") for player_id, info in data["players"].items()}
    reference = tournament.start_date or date.today()
    result = compute_award_candidates(stats, settings, births, reference, await player_of_match_counts(session, tournament_id))
    return {"tournament_id": tournament_id, **result}


async def player_of_tournament_candidates(session: AsyncSession, tournament_id: UUID, weights: AwardWeights) -> dict:
    data = await tournament_statistics_data(session, tournament_id)
    return {
        "award_code": "player_of_tournament",
        "weights": weights.model_dump(),
        "status": "provisional",
        "candidates": player_of_tournament_scores(compute_player_statistics(data), weights),
    }


async def vote_tally(session: AsyncSession, tournament_id: UUID, award_code: str) -> dict:
    decisions = [
        decision for decision in await list_decisions(session, tournament_id, {VOTE_DECISION})
        if decision.payload.get("award_code") == award_code
    ]
    latest = {}
    for decision in decisions:
        latest[decision.payload["voter"]] = decision

    totals: dict = {}
    for decision in latest.values():
        recipient = decision.payload.get("player_id") or decision.payload.get("team_id")
        totals[recipient] = totals.get(recipient, 0) + decision.payload.get("score", 1)

    ranking = sorted(({"recipient_id": key, "score": value} for key, value in totals.items()), key=lambda row: (-row["score"], row["recipient_id"]))
    return {
        "award_code": award_code,
        "votes": [
            {"voter": voter, **{k: v for k, v in decision.payload.items() if k != "voter"}, "reason": decision.reason, "cast_at": decision.created_at}
            for voter, decision in sorted(latest.items())
        ],
        "ranking": ranking,
        "unique_leader": ranking[0]["recipient_id"] if ranking and (len(ranking) == 1 or ranking[0]["score"] != ranking[1]["score"]) else None,
    }
