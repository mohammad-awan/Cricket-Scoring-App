from __future__ import annotations
import csv
import io
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Player, Team, TournamentRoster, TournamentTeam
from app.services.tournament_operations import tournament_calendar
from app.services.tournament_standings import calculate_tournament_standings


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(_cell(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}={_cell(item)}" for key, item in value.items())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def make_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return ",".join(columns) + "\r\n" if columns else ""

    if columns is None:
        columns = []
        for row in rows:
            columns.extend(key for key in row if key not in columns)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _cell(row.get(key)) for key in columns})
    return output.getvalue()


FIXTURE_COLUMNS = [
    "fixture_number", "round_number", "stage", "group_name", "home_team_name", "away_team_name",
    "venue_name", "scheduled_at", "fixture_status", "match_status", "result", "scorecard_url", "fixture_id", "match_id",
]
STANDINGS_COLUMNS = [
    "group_name", "rank", "team_name", "played", "won", "lost", "tied", "no_result", "abandoned", "forfeited",
    "points", "deductions", "bonus_points", "runs_for", "overs_faced", "runs_against", "overs_bowled",
    "net_run_rate", "ranking_unresolved", "adjudicated", "team_id",
]
SCORECARD_COLUMNS = ["fixture_number", "home_team_name", "away_team_name", "result", "scorecard_url", "live_viewer_url", "match_id"]
SQUAD_COLUMNS = ["team_name", "player_name", "role", "is_available", "is_captain", "registration_status", "team_id", "player_id"]


async def fixtures_rows(session: AsyncSession, tournament_id: UUID) -> list[dict]:
    calendar = await tournament_calendar(session, tournament_id)
    rows = [row for day in calendar["days"] for row in day["fixtures"]] + calendar["unscheduled"]
    return [
        {**row, "scorecard_url": row["links"].get("scorecard"), "live_viewer_url": row["links"].get("live_viewer")}
        for row in sorted(rows, key=lambda item: (item["round_number"], item["fixture_number"]))
    ]


async def standings_rows(session: AsyncSession, tournament_id: UUID) -> list[dict]:
    standings = await calculate_tournament_standings(session, tournament_id)
    return [{**row, "group_name": table["group_name"]} for table in standings["tables"] for row in table["standings"]]


async def squad_rows(session: AsyncSession, tournament_id: UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(TournamentTeam, TournamentRoster, Player.full_name, Team.name)
            .join(TournamentRoster, TournamentRoster.tournament_team_id == TournamentTeam.id)
            .join(Player, Player.id == TournamentRoster.player_id)
            .join(Team, Team.id == TournamentTeam.team_id)
            .where(TournamentTeam.tournament_id == tournament_id)
            .order_by(Team.name, Player.full_name)
        )
    ).all()
    return [
        {
            "team_id": membership.team_id,
            "team_name": membership.display_name or team_name,
            "player_id": entry.player_id,
            "player_name": player_name,
            "role": entry.role,
            "is_available": entry.is_available,
            "is_captain": membership.captain_player_id == entry.player_id,
            "registration_status": membership.registration_status,
        }
        for membership, entry, player_name, team_name in rows
    ]
