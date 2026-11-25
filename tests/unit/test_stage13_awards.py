"""Stage 13 award candidates, eligibility and manual-override policy."""

from datetime import date
from uuid import uuid4
import pytest
from app.core.exceptions import ConflictError, ValidationError
from app.schemas.tournament_awards import AwardSettings, AwardWeights, EmergingEligibility
from app.services.tournament_award_management import award_decision
from app.services.tournament_awards import (
    compute_award_candidates,
    emerging_eligibility,
    player_of_tournament_scores,
)


BAT, BOWL, ALL, FIELD = (uuid4() for _ in range(4))


def stats():
    def bat(pid, name, runs, balls, sixes=0, innings=3, matches=3):
        return {"player_id": pid, "player_name": name, "teams": [], "matches": matches, "innings": innings, "runs": runs,
                "balls": balls, "strike_rate": round(runs * 100 / balls, 2) if balls else None, "sixes": sixes}

    def bowl(pid, name, wickets, balls, runs, matches=3):
        return {"player_id": pid, "player_name": name, "teams": [], "matches": matches, "wickets": wickets,
                "legal_balls": balls, "runs_conceded": runs, "economy": round(runs * 6 / balls, 2) if balls else None,
                "average": round(runs / wickets, 2) if wickets else None}

    return {
        "batting": [bat(BAT, "Batter", 300, 200, sixes=10), bat(ALL, "Allrounder", 150, 100, sixes=12), bat(BOWL, "Bowler", 10, 20, innings=1)],
        "bowling": [bowl(BOWL, "Bowler", 12, 120, 120), bowl(ALL, "Allrounder", 6, 72, 60), bowl(FIELD, "Fielder", 0, 6, 20, matches=1)],
        "fielding": [{"player_id": FIELD, "player_name": "Fielder", "teams": [], "matches": 1, "catches": 5, "stumpings": 0,
                      "run_outs": 1, "total_dismissals": 6}],
    }


def test_player_of_tournament_score_is_normalized_and_transparent():
    rows = player_of_tournament_scores(stats(), AwardWeights())
    by_id = {row["player_id"]: row for row in rows}
    assert by_id[BAT]["components"]["runs"] == 1.0
    assert by_id[BOWL]["components"]["wickets"] == 1.0
    assert by_id[ALL]["components"]["batting_efficiency"] == 1.0  # SR 150 is the best
    assert by_id[ALL]["components"]["economy"] == 1.0              # 5.0 economy is the best qualifying
    assert by_id[BOWL]["components"]["economy"] == 0.0              # 6.0 is the worst qualifying
    assert by_id[FIELD]["components"]["economy"] == 0.0              # below the minimum balls
    assert by_id[FIELD]["components"]["fielding"] == 1.0
    weights = AwardWeights()
    for row in rows:
        expected = sum(row["components"][key] * getattr(weights, key) for key in row["components"])
        assert row["award_score"] == pytest.approx(expected, abs=1e-4)
    assert rows == sorted(rows, key=lambda r: (-r["award_score"], -r["runs"], -r["wickets"], r["player_name"], str(r["player_id"])))


def test_minimum_matches_excludes_players():
    rows = player_of_tournament_scores(stats(), AwardWeights(minimum_matches=2))
    assert FIELD not in {row["player_id"] for row in rows}


def test_award_weights_need_one_positive_weight():
    with pytest.raises(ValueError):
        AwardWeights(runs=0, batting_efficiency=0, wickets=0, economy=0, fielding=0)


def test_emerging_eligibility_rules():
    reference = date(2026, 11, 1)
    assert emerging_eligibility(date(2004, 1, 1), EmergingEligibility(), reference) == (False, "Emerging player eligibility is not configured")
    assert emerging_eligibility(None, EmergingEligibility(max_age=23), reference)[0] is False
    assert emerging_eligibility(date(2004, 1, 1), EmergingEligibility(max_age=23), reference)[0] is True
    assert emerging_eligibility(date(2002, 1, 1), EmergingEligibility(max_age=23), reference)[0] is False
    assert emerging_eligibility(date(2002, 1, 1), EmergingEligibility(born_on_or_after=date(2003, 1, 1)), reference)[0] is False


def test_computed_candidates_cover_every_award_and_respect_thresholds():
    settings = AwardSettings(emerging=EmergingEligibility(max_age=23), min_economy_balls=60)
    births = {ALL: date(2005, 5, 5), BAT: date(1990, 1, 1)}
    result = compute_award_candidates(stats(), settings, births, date(2026, 11, 1), {BAT: 2, ALL: 1})
    awards = {award["award_code"]: award for award in result["awards"]}
    assert set(awards) == {"batter_of_tournament", "bowler_of_tournament", "player_of_tournament", "emerging_player",
                           "best_fielder", "most_sixes", "best_economy"}
    assert awards["batter_of_tournament"]["candidates"][0]["player_id"] == BAT
    assert awards["bowler_of_tournament"]["candidates"][0]["player_id"] == BOWL
    assert awards["most_sixes"]["candidates"][0]["player_id"] == ALL
    assert [row["player_id"] for row in awards["best_economy"]["candidates"]] == [ALL, BOWL]
    assert [row["player_id"] for row in awards["emerging_player"]["candidates"]] == [ALL]
    assert awards["best_fielder"]["candidates"][0]["player_id"] == FIELD
    assert result["player_of_match_aggregates"][0]["player_id"] == BAT
    assert all(award["status"] == "provisional_candidates" for award in result["awards"])


def computed(leader=BAT, runner=ALL, unambiguous=True):
    return {"basis": "test", "leader_unambiguous": unambiguous,
            "all_candidates": [{"player_id": leader, "player_name": "Leader"}, {"player_id": runner, "player_name": "Runner"}]}


def test_confirming_the_unambiguous_leader_is_statistical():
    method, details = award_decision("statistical_leader", BAT, computed())
    assert method == "statistical"
    assert details["override"] is False and details["recipient_computed_rank"] == 1


def test_selecting_another_player_is_a_recorded_manual_override():
    method, details = award_decision("organizer_selection", ALL, computed())
    assert method == "manual"
    assert details["override"] is True
    assert details["computed_leader"]["player_id"] == str(BAT)
    assert details["recipient_computed_rank"] == 2


def test_statistical_claims_must_match_the_evidence():
    with pytest.raises(ConflictError):
        award_decision("statistical_leader", ALL, computed())
    with pytest.raises(ConflictError):
        award_decision("statistical_leader", BAT, computed(unambiguous=False))
    with pytest.raises(ValidationError):
        award_decision("statistical_leader", BAT, None)


def test_manual_award_without_computed_ranking_is_not_an_override():
    method, details = award_decision("organizer_selection", uuid4(), None)
    assert method == "manual" and "override" not in details


def test_committee_vote_requires_enabled_voting_and_unique_winner():
    tally = {"unique_leader": str(ALL), "ranking": [{"recipient_id": str(ALL), "score": 3}]}
    with pytest.raises(ConflictError):
        award_decision("committee_vote", ALL, computed(), voting_enabled=False, tally=tally)
    with pytest.raises(ConflictError):
        award_decision("committee_vote", BAT, computed(), voting_enabled=True, tally=tally)
    method, details = award_decision("committee_vote", ALL, computed(), voting_enabled=True, tally=tally)
    assert method == "manual" and details["committee_tally"] == tally["ranking"] and details["override"] is True
