"""Tournament completion, championship freeze and reopening.

Finalization validates every published fixture result/disposition,
standings consistency, bracket resolution, champion determination and
award publication, then freezes an auditable snapshot that remains
reproducible after roster transfers, team/player renames or rule
changes.

Reopening policy (``REOPENING_POLICY``):

* Only a COMPLETED tournament can be reopened; ARCHIVED editions are
  permanent historical records.
* A reason of at least 10 characters is mandatory and the previous
  frozen snapshot is preserved in the immutable decision log.
* Reopening unfreezes the closeout, returns the tournament to LIVE and
  unpublishes awards, so results, standings and awards must be reviewed
  and republished before the next finalization (revision + 1).
"""

from __future__ import annotations
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    Player,
    Team,
    Tournament,
    TournamentRoster,
    TournamentStatus,
    TournamentTeam,
)
from app.models.entities.fixtures import FixtureBracketDependency
from app.models.entities.tournament_operations import TournamentAward, TournamentCloseout
from app.repositories.tournaments import TournamentRepository
from app.services.tournament_award_management import (
    publication_state,
    serialize_award,
    unpublish_awards,
)
from app.services.tournament_decisions import record_decision
from app.services.tournament_qualification import SlotResolver
from app.services.tournament_results import (
    LEAGUE_STAGES,
    current_dispositions,
    fixture_outcomes,
    published_fixtures,
    result_text,
)
from app.services.tournament_standings import calculate_tournament_standings, get_standings_rules
from app.services.tournament_statistics import (
    compute_player_statistics,
    compute_records,
    compute_team_statistics,
    tournament_statistics_data,
)
from app.services.tournaments import locked_tournament, tournament_audit, tournament_transaction


REOPENING_POLICY = [
    "Only a completed tournament can be reopened; archived editions are permanent.",
    "A reason of at least 10 characters is required and the previous frozen snapshot is kept in the decision log.",
    "Reopening returns the tournament to live, unfreezes the closeout and unpublishes awards.",
    "Results, standings and awards must be reviewed and awards republished before finalizing again (new revision).",
]
FINALIZABLE_STATUSES = {TournamentStatus.LIVE, TournamentStatus.SCHEDULED, TournamentStatus.ACTIVE}
LEAGUE_STRUCTURES = {"single_round_robin", "double_round_robin"}


async def _bracket_checks(session: AsyncSession, tournament_id: UUID, fixtures) -> list[str]:
    blockers = []
    resolver = SlotResolver(session, tournament_id)
    by_run = defaultdict(dict)
    for item in fixtures:
        by_run[item.fixture.generation_run_id][item.fixture.fixture_number] = item.fixture

    dependency_sources = {}
    fixture_ids = [item.fixture.id for item in fixtures]
    if fixture_ids:
        id_to_number = {item.fixture.id: item.fixture.fixture_number for item in fixtures}
        for dependency in (
            await session.scalars(
                select(FixtureBracketDependency).where(FixtureBracketDependency.fixture_id.in_(fixture_ids))
            )
        ).all():
            if dependency.source_fixture_id not in id_to_number:
                blockers.append(f"Broken bracket dependency {dependency.id}")
                continue
            dependency_sources[(dependency.fixture_id, dependency.target_side)] = (
                f"{dependency.advancement}:{id_to_number[dependency.source_fixture_id]}"
            )

    for item in fixtures:
        fixture = item.fixture
        if fixture.status == "cancelled":
            continue
        for side in ("home", "away"):
            source = dependency_sources.get((fixture.id, side)) or getattr(item, f"{side}_source")
            if not source:
                continue
            expected, message = await resolver.resolve(source, by_run[fixture.generation_run_id])
            actual = getattr(fixture, f"{side}_team_id")
            if expected is None:
                blockers.append(f"Fixture {fixture.fixture_number} {side} slot ({source}) is unresolved: {message}")
            elif actual != expected:
                blockers.append(f"Fixture {fixture.fixture_number} {side} slot does not match its official source ({source})")

    return blockers


async def determine_champion(session: AsyncSession, tournament_id: UUID) -> dict:
    _, rules = await get_standings_rules(session, tournament_id)

    if rules.structure in LEAGUE_STRUCTURES:
        standings = await calculate_tournament_standings(session, tournament_id)

        if standings["pending_fixtures"] or standings["disputed_fixtures"]:
            raise ConflictError("League fixtures are unfinished or disputed")
        if len(standings["tables"]) != 1:
            raise ConflictError("League champion requires exactly one standings table")

        rows = standings["tables"][0]["standings"]
        if not rows:
            raise ConflictError("League standings are empty")
        if rows[0]["ranking_unresolved"]:
            raise ConflictError("First place is tied and requires an adjudicated placement")

        return {
            "method": "league_table",
            "champion_team_id": rows[0]["team_id"],
            "runner_up_team_id": rows[1]["team_id"] if len(rows) > 1 and not rows[1]["ranking_unresolved"] else None,
            "ruleset_version": standings["ruleset_version"],
            "adjudicated": rows[0].get("adjudicated", False),
        }

    fixtures = [
        item for item in await published_fixtures(session, tournament_id, include_cancelled=False)
        if item.stage not in LEAGUE_STAGES
    ]
    if not fixtures:
        raise ConflictError("No published knockout fixtures exist")

    outcomes, _ = await fixture_outcomes(session, tournament_id, fixtures)
    fixtures = [item for item in fixtures if outcomes[item.fixture.id].outcome != "excluded"]
    final_round = max(item.round_number for item in fixtures)
    finals = [item for item in fixtures if item.round_number == final_round]
    pairs = {frozenset({item.fixture.home_team_id, item.fixture.away_team_id}) for item in finals}

    if len(pairs) != 1 or None in next(iter(pairs)):
        raise ConflictError("Knockout final could not be identified unambiguously")

    required = max(rules.best_of_finals // 2 + 1, 1)
    wins = defaultdict(int)
    for item in finals:
        outcome = outcomes[item.fixture.id]
        if not outcome.is_final and len(finals) == 1:
            raise ConflictError("Knockout final is not completed")
        if outcome.advancing_team_id is not None:
            wins[outcome.advancing_team_id] += 1

    leaders = [team for team, count in wins.items() if count >= required] if len(finals) > 1 else list(wins)
    if len(leaders) != 1:
        raise ConflictError("Knockout final has no resolved winner; record an advancement adjudication if it was tied")

    champion = leaders[0]
    pair = next(iter(pairs))
    return {
        "method": "knockout_final" if len(finals) == 1 else f"best_of_{rules.best_of_finals}_final",
        "champion_team_id": champion,
        "runner_up_team_id": next(team for team in pair if team != champion),
        "final_fixture_ids": [item.fixture.id for item in finals],
        "final_match_ids": [item.fixture.match_id for item in finals if item.fixture.match_id],
        "final_wins": dict(wins),
    }


async def closeout_readiness(session: AsyncSession, tournament_id: UUID) -> dict:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    blockers, warnings = [], []
    fixtures = await published_fixtures(session, tournament_id)

    if not fixtures:
        blockers.append("No published fixtures exist")

    outcomes, _ = await fixture_outcomes(session, tournament_id, fixtures)
    fixture_checks = {"total": len(fixtures), "final": 0, "pending": 0, "disputed": 0}

    for item in fixtures:
        fixture, outcome = item.fixture, outcomes[item.fixture.id]
        label = f"Fixture {fixture.fixture_number}"

        if item.review_message:
            blockers.append(f"{label}: {item.review_message}")
        if outcome.outcome == "disputed":
            fixture_checks["disputed"] += 1
            blockers.append(f"{label}: completed match has no valid result and requires review")
        elif not outcome.is_final:
            fixture_checks["pending"] += 1
            state = "is postponed" if fixture.status == "postponed" else "has no official result or disposition"
            blockers.append(f"{label} {state}")
        else:
            fixture_checks["final"] += 1
            if item.stage not in LEAGUE_STAGES and outcome.outcome != "excluded" and outcome.advancing_team_id is None:
                blockers.append(f"{label}: knockout result needs an advancement adjudication")

    bracket_blockers = await _bracket_checks(session, tournament_id, fixtures)
    blockers.extend(bracket_blockers)

    standings = None
    try:
        standings = await calculate_tournament_standings(session, tournament_id)
        warnings.extend(standings["warnings"])
    except ConflictError as error:
        blockers.append(f"Standings: {error}")

    champion = None
    try:
        champion = await determine_champion(session, tournament_id)
    except ConflictError as error:
        blockers.append(f"Champion: {error}")

    awards = await publication_state(session, tournament_id)
    if not awards["published"]:
        blockers.append("Awards must be reviewed, confirmed and published before finalization")

    return {
        "tournament_id": tournament_id,
        "status": tournament.status,
        "ready_to_finalize": not blockers and tournament.status in FINALIZABLE_STATUSES,
        "blockers": blockers,
        "warnings": warnings,
        "checks": {
            "fixtures": fixture_checks,
            "bracket_unresolved": len(bracket_blockers),
            "standings_unresolved": bool(standings and standings["ranking_unresolved"]),
            "awards_published": awards["published"],
        },
        "champion": champion,
        "reopening_policy": REOPENING_POLICY,
    }


async def closeout_blockers(session: AsyncSession, tournament_id: UUID) -> list[str]:
    return (await closeout_readiness(session, tournament_id))["blockers"]


async def build_closeout_snapshot(session: AsyncSession, tournament_id: UUID, championship: dict) -> dict:
    version, rules = await get_standings_rules(session, tournament_id)
    standings = await calculate_tournament_standings(session, tournament_id)
    data = await tournament_statistics_data(session, tournament_id)
    fixtures = await published_fixtures(session, tournament_id)
    outcomes, match_map = await fixture_outcomes(session, tournament_id, fixtures)

    memberships = (await session.scalars(select(TournamentTeam).where(TournamentTeam.tournament_id == tournament_id))).all()
    team_ids = {membership.team_id for membership in memberships}
    team_names = dict((await session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()) if team_ids else {}
    team_names.update({membership.team_id: membership.display_name or team_names.get(membership.team_id) for membership in memberships})
    roster_rows = (
        await session.execute(
            select(TournamentRoster, Player.full_name)
            .join(Player, Player.id == TournamentRoster.player_id)
            .where(TournamentRoster.tournament_team_id.in_([membership.id for membership in memberships]))
        )
    ).all() if memberships else []
    membership_team = {membership.id: membership.team_id for membership in memberships}

    awards = (
        await session.scalars(
            select(TournamentAward).where(TournamentAward.tournament_id == tournament_id, TournamentAward.status == "confirmed")
        )
    ).all()
    player_names = {player_id: info.get("name") for player_id, info in data["players"].items()}

    return {
        "schema_version": 2,
        "tournament_id": str(tournament_id),
        "ruleset": {"id": version.id, "version": version.version, "checksum": version.checksum, "rules": rules.model_dump(mode="json")},
        "champion_team_id": str(championship["champion_team_id"]),
        "champion_team_name": team_names.get(championship["champion_team_id"]),
        "championship": championship,
        "standings": standings,
        "results": [
            {
                "fixture_id": item.fixture.id,
                "fixture_number": item.fixture.fixture_number,
                "stage": item.stage,
                "round_number": item.round_number,
                "home_team_id": item.fixture.home_team_id,
                "home_team_name": team_names.get(item.fixture.home_team_id),
                "away_team_id": item.fixture.away_team_id,
                "away_team_name": team_names.get(item.fixture.away_team_id),
                "match_id": item.fixture.match_id,
                "outcome": outcomes[item.fixture.id].outcome,
                "advancing_team_id": outcomes[item.fixture.id].advancing_team_id,
                "result": result_text(outcomes[item.fixture.id], team_names),
                "completed_at": match_map[item.fixture.match_id].completed_at if item.fixture.match_id in match_map else None,
            }
            for item in fixtures
        ],
        "dispositions": list((await current_dispositions(session, tournament_id)).values()),
        "leaderboards": compute_player_statistics(data),
        "team_statistics": compute_team_statistics(data),
        "records": compute_records(data),
        "teams": [
            {"team_id": membership.team_id, "team_name": team_names.get(membership.team_id),
             "registration_status": membership.registration_status, "is_reserve": membership.is_reserve}
            for membership in memberships
        ],
        "squads": [
            {"team_id": membership_team.get(entry.tournament_team_id), "team_name": team_names.get(membership_team.get(entry.tournament_team_id)),
             "player_id": entry.player_id, "player_name": name, "role": entry.role}
            for entry, name in roster_rows
        ],
        "awards": [
            {**serialize_award(award), "player_name": player_names.get(award.player_id), "team_name": team_names.get(award.team_id)}
            for award in awards
        ],
    }


async def finalize_tournament(session: AsyncSession, tournament_id: UUID, *, actor_id: str | None = None) -> TournamentCloseout:
    async with tournament_transaction(session, "Tournament finalization"):
        tournament = await locked_tournament(TournamentRepository(session), tournament_id)

        if tournament.status not in FINALIZABLE_STATUSES:
            raise ConflictError("Tournament cannot be finalized from its current status")

        readiness = await closeout_readiness(session, tournament_id)
        if readiness["blockers"]:
            raise ConflictError("Cannot finalize: " + "; ".join(readiness["blockers"][:10]))

        championship = readiness["champion"]
        champion_team_id = championship["champion_team_id"]
        membership = await session.scalar(
            select(TournamentTeam).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.team_id == champion_team_id,
                TournamentTeam.registration_status == "approved",
                TournamentTeam.is_reserve.is_(False),
            )
        )
        if membership is None:
            raise ValidationError("Champion must be an approved participating team")

        existing = await session.scalar(
            select(TournamentCloseout).where(TournamentCloseout.tournament_id == tournament_id).with_for_update()
        )
        if existing is not None and existing.is_frozen:
            raise ConflictError("Tournament already finalized")

        now = datetime.now(UTC)
        snapshot = await build_closeout_snapshot(session, tournament_id, championship)
        snapshot["finalized_at"] = now.isoformat()
        snapshot["warnings"] = readiness["warnings"]
        snapshot = jsonable_encoder(snapshot)

        if existing is None:
            closeout = TournamentCloseout(
                tournament_id=tournament_id, champion_team_id=champion_team_id, snapshot=snapshot,
                revision=1, is_frozen=True, finalized_by=actor_id, finalized_at=now,
            )
            session.add(closeout)
        else:
            closeout = existing
            closeout.champion_team_id = champion_team_id
            closeout.snapshot = snapshot
            closeout.revision += 1
            closeout.is_frozen = True
            closeout.finalized_by = actor_id
            closeout.finalized_at = now
            closeout.reopened_at = None
            closeout.reopen_reason = None

        tournament.status = TournamentStatus.COMPLETED
        tournament_audit(
            session, tournament_id, "tournament_finalized",
            {"champion_team_id": str(champion_team_id), "closeout_revision": closeout.revision},
            actor_id=actor_id,
        )
        await session.flush()
        record_decision(
            session, tournament_id, "tournament_finalized", "Official tournament finalization",
            {"revision": closeout.revision, "champion_team_id": champion_team_id, "snapshot": closeout.snapshot},
            subject_id=closeout.id, actor_id=actor_id,
        )
        await session.flush()
        return closeout


async def reopen_tournament(session: AsyncSession, tournament_id: UUID, reason: str, *, actor_id: str | None = None) -> TournamentCloseout:
    reason = reason.strip()

    if len(reason) < 10:
        raise ValidationError("A reopening reason of at least 10 characters is required")

    async with tournament_transaction(session, "Tournament reopening"):
        tournament = await locked_tournament(TournamentRepository(session), tournament_id)

        if tournament.status != TournamentStatus.COMPLETED:
            raise ConflictError("Only completed tournaments can be reopened; archived editions are permanent")

        closeout = await session.scalar(
            select(TournamentCloseout).where(TournamentCloseout.tournament_id == tournament_id).with_for_update()
        )
        if closeout is None or not closeout.is_frozen:
            raise NotFoundError("Frozen closeout record not found")

        record_decision(
            session, tournament_id, "tournament_reopened", reason,
            {"previous_revision": closeout.revision, "previous_champion_team_id": closeout.champion_team_id,
             "previous_snapshot": closeout.snapshot, "policy": REOPENING_POLICY},
            subject_id=closeout.id, actor_id=actor_id,
        )
        closeout.is_frozen = False
        closeout.reopened_at = datetime.now(UTC)
        closeout.reopen_reason = reason
        tournament.status = TournamentStatus.LIVE

        if (await publication_state(session, tournament_id))["published"]:
            await unpublish_awards(session, tournament_id, f"Tournament reopened: {reason}", actor_id=actor_id, allow_closed=True)

        tournament_audit(
            session, tournament_id, "tournament_reopened",
            {"reason": reason, "previous_champion_team_id": str(closeout.champion_team_id), "closeout_revision": closeout.revision},
            actor_id=actor_id,
        )
        await session.flush()
        return closeout


async def official_record(session: AsyncSession, tournament_id: UUID) -> dict:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    closeout = await session.scalar(select(TournamentCloseout).where(TournamentCloseout.tournament_id == tournament_id))
    if closeout is None:
        raise NotFoundError("This tournament has not been finalized")

    return {
        "tournament_id": tournament_id,
        "tournament_name": tournament.name,
        "season": tournament.season,
        "status": tournament.status,
        "revision": closeout.revision,
        "is_frozen": closeout.is_frozen,
        "finalized_at": closeout.finalized_at,
        "reopened_at": closeout.reopened_at,
        "reopen_reason": closeout.reopen_reason,
        "champion_team_id": closeout.champion_team_id,
        "snapshot": closeout.snapshot,
        "reopening_policy": REOPENING_POLICY,
    }


async def series_history(session: AsyncSession, series_id: UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Tournament, TournamentCloseout)
            .outerjoin(TournamentCloseout, TournamentCloseout.tournament_id == Tournament.id)
            .where(Tournament.series_id == series_id)
            .order_by(Tournament.edition_number, Tournament.start_date)
        )
    ).all()

    return [
        {
            "tournament_id": tournament.id,
            "name": tournament.name,
            "season": tournament.season,
            "edition_number": tournament.edition_number,
            "status": tournament.status,
            "finalized": closeout is not None and closeout.is_frozen,
            "revision": closeout.revision if closeout else None,
            "champion_team_id": closeout.champion_team_id if closeout and closeout.is_frozen else None,
            "champion_team_name": (closeout.snapshot or {}).get("champion_team_name") if closeout and closeout.is_frozen else None,
            "awards": [
                {"award_code": award.get("award_code"), "title": award.get("title"),
                 "player_name": award.get("player_name"), "team_name": award.get("team_name")}
                for award in ((closeout.snapshot or {}).get("awards", []) if closeout and closeout.is_frozen else [])
                if not str(award.get("award_code", "")).startswith("player_of_match:")
            ],
        }
        for tournament, closeout in rows
    ]
