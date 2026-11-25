"""Stage 13 exports and printable report."""

from uuid import uuid4
from app.services.tournament_exports import make_csv
from app.services.tournament_reports import render_report_html


def test_csv_flattens_nested_values_and_keeps_column_order():
    team = uuid4()
    content = make_csv([{"team_name": "Alpha", "form": ["W", "L"], "team_id": team, "note": None}], ["team_name", "form", "team_id", "note"])
    header, row = content.strip().splitlines()
    assert header == "team_name,form,team_id,note"
    assert row == f"Alpha,W; L,{team},"
    assert make_csv([], ["a", "b"]).strip() == "a,b"


def test_printable_report_escapes_user_content():
    report = {
        "tournament": {"name": "<script>alert(1)</script> Cup", "season": "2026", "organizer": "Org", "start_date": None, "end_date": None},
        "championship": {"champion_team_name": "Alpha & Co", "revision": 1, "finalized_at": "2026-11-25"},
        "standings": {"tables": [{"group_name": "League", "standings": [{
            "rank": 1, "team_name": "Alpha & Co", "played": 1, "won": 1, "lost": 0, "tied": 0, "no_result": 0,
            "abandoned": 0, "points": 2, "net_run_rate": 1.5}]}]},
        "fixtures": [{"fixture_number": 1, "home_team_name": "Alpha & Co", "away_team_name": "Bravo", "result": "Alpha & Co won by 5 runs"}],
        "leaderboards": {"batting": [], "bowling": [], "fielding": []},
        "awards": [],
        "awards_published": False,
    }
    html = render_report_html(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Alpha &amp; Co" in html and "+1.500" in html
