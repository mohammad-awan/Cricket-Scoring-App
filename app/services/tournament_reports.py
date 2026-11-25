from __future__ import annotations
from html import escape
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError
from app.models import Tournament
from app.models.entities.tournament_operations import TournamentCloseout
from app.services.tournament_award_management import list_confirmed_awards
from app.services.tournament_standings import calculate_tournament_standings


async def build_tournament_report(
    session: AsyncSession,
    tournament_id: UUID,
) -> dict:
    """Tournament summary: standings, results, leaderboards, records, squads, awards."""

    from app.services.tournament_award_management import publication_state, serialize_award
    from app.services.tournament_exports import fixtures_rows, squad_rows
    from app.services.tournament_statistics import (
        compute_player_statistics,
        compute_records,
        compute_team_statistics,
        tournament_statistics_data,
    )

    tournament = await session.get(Tournament, tournament_id)

    if tournament is None:
        raise NotFoundError("Tournament not found")

    standings = await calculate_tournament_standings(session, tournament_id)
    data = await tournament_statistics_data(session, tournament_id)
    statistics = compute_player_statistics(data)
    fixtures = await fixtures_rows(session, tournament_id)
    awards = await list_confirmed_awards(session, tournament_id)
    player_names = {player_id: info.get("name") for player_id, info in data["players"].items()}
    team_names = {row["team_id"]: row["team_name"] for table in standings["tables"] for row in table["standings"]}

    closeout = await session.scalar(
        select(TournamentCloseout).where(
            TournamentCloseout.tournament_id
            == tournament_id
        )
    )

    championship = None
    if closeout is not None and closeout.is_frozen:
        championship = {
            **closeout.snapshot.get("championship", {}),
            "champion_team_name": closeout.snapshot.get("champion_team_name"),
            "revision": closeout.revision,
            "finalized_at": closeout.finalized_at,
        }

    return jsonable_encoder({
        "tournament": {
            "id": tournament.id,
            "name": tournament.name,
            "season": tournament.season,
            "organizer": tournament.organizer,
            "status": tournament.status,
            "start_date": tournament.start_date,
            "end_date": tournament.end_date,
        },
        "standings": standings,
        "leaderboards": statistics,
        "team_records": compute_team_statistics(data),
        "records": compute_records(data),
        "fixtures": fixtures,
        "squads": await squad_rows(session, tournament_id),
        "awards": [
            {**serialize_award(award), "player_name": player_names.get(award.player_id),
             "team_name": team_names.get(award.team_id)}
            for award in awards
        ],
        "awards_published": (await publication_state(session, tournament_id))["published"],
        "championship": championship,
    })


def safe(value) -> str:
    return escape("" if value is None else str(value))


def _table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{safe(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{safe(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_report_html(report: dict) -> str:
    tournament = report["tournament"]
    sections = []
    championship = report.get("championship")

    if championship:
        sections.append(
            "<h2>Champion</h2>"
            f"<p class=\"champion\">{safe(championship.get('champion_team_name') or championship.get('champion_team_id'))}</p>"
            f"<p class=\"muted\">Official closeout revision {safe(championship.get('revision'))}, "
            f"finalized {safe(championship.get('finalized_at'))}</p>"
        )

    for group in report["standings"]["tables"]:
        sections.append(
            f"<h2>{safe(group['group_name'])} table</h2>"
            + _table(
                ["#", "Team", "P", "W", "L", "T", "NR", "Pts", "NRR"],
                [[row["rank"], row["team_name"], row["played"], row["won"], row["lost"], row["tied"],
                  row["no_result"] + row["abandoned"], row["points"], f"{row['net_run_rate']:+.3f}"]
                 for row in group["standings"]],
            )
        )

    results = [row for row in report["fixtures"] if row.get("result")]
    if results:
        sections.append(
            "<h2>Results</h2>"
            + _table(["#", "Fixture", "Result"],
                     [[row["fixture_number"], f"{row['home_team_name']} v {row['away_team_name']}", row["result"]] for row in results])
        )

    leaders = report["leaderboards"]
    sections.append(
        "<h2>Most runs</h2>"
        + _table(["Player", "Inns", "Runs", "HS", "Avg", "SR", "4s", "6s"],
                 [[row["player_name"], row["innings"], row["runs"], row["highest_score_display"], row["average"] or "-",
                   row["strike_rate"] or "-", row["fours"], row["sixes"]] for row in leaders["batting"][:10]])
    )
    sections.append(
        "<h2>Most wickets</h2>"
        + _table(["Player", "Overs", "Wkts", "Runs", "Econ", "Avg", "Best"],
                 [[row["player_name"], row["overs"], row["wickets"], row["runs_conceded"], row["economy"] or "-",
                   row["average"] or "-", row["best_figures_display"]] for row in leaders["bowling"][:10]])
    )
    if leaders["fielding"]:
        sections.append(
            "<h2>Fielding</h2>"
            + _table(["Player", "Ct", "St", "RO", "Total"],
                     [[row["player_name"], row["catches"], row["stumpings"], row["run_outs"], row["total_dismissals"]]
                      for row in leaders["fielding"][:10]])
        )

    awards = [award for award in report["awards"] if award["category"] != "player_of_match"]
    if awards:
        sections.append(
            "<h2>Awards" + ("" if report.get("awards_published") else " (unpublished)") + "</h2>"
            + _table(["Award", "Recipient", "Basis"],
                     [[award["title"], award.get("player_name") or award.get("team_name"), award.get("basis") or award["selection_method"]]
                      for award in awards])
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{safe(tournament['name'])}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
        th, td {{ border: 1px solid #999; padding: 6px 8px; text-align: left; }}
        th {{ background: #eee; }}
        .champion {{ font-size: 1.4em; font-weight: bold; }}
        .muted {{ color: #555; }}
        @media print {{ h2 {{ page-break-after: avoid; }} table {{ page-break-inside: auto; }} }}
    </style>
</head>
<body>
    <h1>{safe(tournament['name'])}</h1>
    <p class="muted">{safe(tournament.get('season'))} {safe(tournament.get('organizer'))}
       {safe(tournament.get('start_date'))} – {safe(tournament.get('end_date'))}</p>
    {"".join(sections)}
</body>
</html>"""
