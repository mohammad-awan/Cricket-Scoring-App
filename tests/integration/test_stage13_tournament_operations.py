
"""
PostgreSQL integration tests for tournament operations.

Requirements:
    - A separate PostgreSQL test database.
    - All Alembic migrations applied.
    - TEST_DATABASE_URL configured.

The shared database fixture rolls back test data.
"""

from __future__ import annotations
from copy import deepcopy
from datetime import UTC, datetime
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from app.core.exceptions import ConflictError
from app.models import Match, MatchStatus, TournamentStatus
from app.models.entities.fixtures import Fixture, FixtureBracketDependency, FixtureChangeAudit
from app.models.entities.tournament_operations import TournamentAward, TournamentCloseout, TournamentDecision
from app.services.tournament_award_management import (
    confirm_award,
    revoke_award,
    publish_awards,
    publication_state,
)
from app.services.tournament_closeout import closeout_readiness, finalize_tournament, reopen_tournament
from app.services.tournament_decisions import list_decisions
from app.services.tournament_bracket import advance_bracket_dependency, BracketAdvancementConflict
from tests.integration.test_stage12_fixture_persistence import database, competition, save_draft


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


AWARD_CODE = "fair_play"


# --------------------------------------------------
# Shared helpers
# --------------------------------------------------


async def prepare_knockout(database, competition):

    tournament, request = competition
    service, run_id, fixtures, _ = await save_draft(
        database,
        competition,
        "knockout",
    )
    await service.publish(
        run_id,
        {
            fixture.id: fixture.version
            for fixture in fixtures
        },
        "Publish official integration test fixtures",
    )
    await database.commit()
    tournament.status = TournamentStatus.LIVE
    await database.flush()

    return tournament, service, run_id


async def complete_match(database, match_id):

    match = await database.get(Match, match_id)
    assert match is not None
    match.status = MatchStatus.COMPLETED
    match.winner_team_id = match.team_a_id
    match.result_type = "runs"
    match.result_margin = 10
    match.completed_at = datetime.now(UTC)
    await database.flush()

    return match


async def prepare_completed_tournament(database, competition):
    tournament, service, run_id = (
        await prepare_knockout(
            database,
            competition,
        )
    )

    fixtures = await service.repo.fixtures(run_id)

    first_round = [
        fixture
        for fixture in fixtures
        if fixture.match_id is not None
    ]

    assert len(first_round) == 2

    for fixture in first_round:

        await complete_match(
            database,
            fixture.match_id,
        )

    await service.progress(run_id)

    await database.flush()

    fixtures = await service.repo.fixtures(run_id)

    final = next(
        fixture
        for fixture in fixtures
        if fixture.fixture_number == 3
    )

    assert final.match_id is not None

    final_match = await complete_match(
        database,
        final.match_id,
    )

    await service.progress(run_id)

    await database.commit()

    return (
        tournament,
        final_match.winner_team_id,
    )


async def confirm_team_award(
    database,
    tournament_id,
    team_id,
):

    award = await confirm_award(
        database,
        tournament_id,
        AWARD_CODE,
        team_id=team_id,
        reason=(
            "Official fair play award for "
            "integration testing"
        ),
        basis="organizer_selection",
        actor_id="integration-test",
    )

    await database.commit()

    return award


async def prepare_finalizable_tournament(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_completed_tournament(
            database,
            competition,
        )
    )

    await confirm_team_award(
        database,
        tournament.id,
        champion_id,
    )

    await publish_awards(
        database,
        tournament.id,
        "Publish approved tournament awards",
        actor_id="integration-test",
    )

    await database.commit()

    return tournament, champion_id


# --------------------------------------------------
# Award persistence
# --------------------------------------------------


async def test_award_confirmation_and_revocation_history(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_completed_tournament(
            database,
            competition,
        )
    )

    award = await confirm_team_award(
        database,
        tournament.id,
        champion_id,
    )

    award_id = award.id

    database.expire_all()

    stored = await database.get(
        TournamentAward,
        award_id,
    )

    assert stored is not None
    assert stored.status == "confirmed"
    assert stored.team_id == champion_id
    assert stored.player_id is None

    tournament_id = stored.tournament_id

    revoked = await revoke_award(
        database,
        tournament_id,
        AWARD_CODE,
        "Revoke award for official review",
        actor_id="integration-test",
    )

    await database.commit()

    assert revoked.status == "revoked"

    decisions = await list_decisions(
        database,
        tournament_id,
        {
            "award_confirmed",
            "award_revoked",
        },
    )

    assert len(decisions) == 2

    history = {
        decision.decision_type: decision
        for decision in decisions
    }

    assert (
        history["award_confirmed"]
        .payload["team_id"]
        == str(champion_id)
    )

    assert (
        history["award_revoked"]
        .payload["previous_team_id"]
        == str(champion_id)
    )

    assert all(
        decision.subject_id == award_id
        for decision in decisions
    )


async def test_duplicate_award_confirmation_is_rejected(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_completed_tournament(
            database,
            competition,
        )
    )

    tournament_id = tournament.id

    await confirm_team_award(
        database,
        tournament_id,
        champion_id,
    )

    with pytest.raises(ConflictError):

        async with database.begin_nested():

            await confirm_award(
                database,
                tournament_id,
                AWARD_CODE,
                team_id=champion_id,
                reason="Attempt duplicate award confirmation",
                basis="organizer_selection",
            )

    count = await database.scalar(
        select(func.count(TournamentAward.id))
        .where(
            TournamentAward.tournament_id
            == tournament_id,
            TournamentAward.award_code
            == AWARD_CODE,
        )
    )

    assert count == 1


# --------------------------------------------------
# Database-level immutable decision history
# --------------------------------------------------


async def test_decision_history_cannot_be_updated_or_deleted(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_completed_tournament(
            database,
            competition,
        )
    )

    tournament_id = tournament.id

    await confirm_team_award(
        database,
        tournament_id,
        champion_id,
    )

    decisions = await list_decisions(
        database,
        tournament_id,
        {"award_confirmed"},
    )

    assert len(decisions) == 1

    decision_id = decisions[0].id
    original_reason = decisions[0].reason
    original_payload = deepcopy(
        decisions[0].payload
    )

    # Verify that PostgreSQL itself rejects updates.

    with pytest.raises(
        DBAPIError,
        match="immutable",
    ):

        async with database.begin_nested():

            await database.execute(
                update(TournamentDecision)
                .where(
                    TournamentDecision.id
                    == decision_id
                )
                .values(
                    reason="Unauthorized modification"
                )
            )

    # Verify that PostgreSQL itself rejects deletes.

    with pytest.raises(
        DBAPIError,
        match="immutable",
    ):

        async with database.begin_nested():

            await database.execute(
                delete(TournamentDecision)
                .where(
                    TournamentDecision.id
                    == decision_id
                )
            )

    database.expire_all()

    stored = await database.get(
        TournamentDecision,
        decision_id,
    )

    assert stored is not None
    assert stored.reason == original_reason
    assert stored.payload == original_payload


# --------------------------------------------------
# Bracket advancement
# --------------------------------------------------


async def test_bracket_advancement_is_persistent_and_idempotent(
    database,
    competition,
):

    tournament, service, run_id = (
        await prepare_knockout(
            database,
            competition,
        )
    )

    fixtures = await service.repo.fixtures(run_id)

    source = next(
        fixture
        for fixture in fixtures
        if fixture.match_id is not None
    )

    dependency = await database.scalar(
        select(FixtureBracketDependency)
        .where(
            FixtureBracketDependency.source_fixture_id
            == source.id
        )
        .limit(1)
    )

    assert dependency is not None

    dependency_id = dependency.id
    target_id = dependency.fixture_id
    target_side = dependency.target_side

    match = await complete_match(
        database,
        source.match_id,
    )

    winner_id = match.winner_team_id

    target = await database.get(
        Fixture,
        target_id,
    )

    original_version = target.version

    result = await advance_bracket_dependency(
        database,
        dependency_id,
        reason="Advance official semifinal winner",
    )

    await database.commit()

    assert result["changed"] is True
    assert result["advancing_team_id"] == winner_id

    await database.refresh(target)

    assert (
        getattr(
            target,
            f"{target_side}_team_id",
        )
        == winner_id
    )

    assert target.version == original_version + 1

    replay = await advance_bracket_dependency(
        database,
        dependency_id,
    )

    assert replay["changed"] is False
    assert replay["status"] == "already_assigned"

    await database.refresh(target)

    assert target.version == original_version + 1

    audit_count = await database.scalar(
        select(func.count(FixtureChangeAudit.id))
        .where(
            FixtureChangeAudit.fixture_id
            == target_id,
            FixtureChangeAudit.action
            == "bracket_advancement",
        )
    )

    assert audit_count == 1


async def test_corrected_result_cannot_overwrite_linked_final(
    database,
    competition,
):

    tournament, service, run_id = (
        await prepare_knockout(
            database,
            competition,
        )
    )

    fixtures = await service.repo.fixtures(run_id)

    sources = [
        fixture
        for fixture in fixtures
        if fixture.match_id is not None
    ]

    assert len(sources) == 2

    for source in sources:

        await complete_match(
            database,
            source.match_id,
        )

    await service.progress(run_id)

    await database.commit()

    final = next(
        fixture
        for fixture in await service.repo.fixtures(
            run_id
        )
        if fixture.fixture_number == 3
    )

    assert final.match_id is not None

    final_id = final.id
    final_match_id = final.match_id

    original_home = final.home_team_id
    original_away = final.away_team_id
    original_version = final.version

    source = sources[0]

    dependency = await database.scalar(
        select(FixtureBracketDependency)
        .where(
            FixtureBracketDependency.source_fixture_id
            == source.id,
            FixtureBracketDependency.fixture_id
            == final_id,
        )
    )

    assert dependency is not None

    dependency_id = dependency.id

    source_match = await database.get(
        Match,
        source.match_id,
    )

    # Simulate an official result correction.

    source_match.winner_team_id = (
        source_match.team_b_id
    )

    await database.flush()

    with pytest.raises(
        BracketAdvancementConflict,
    ):

        async with database.begin_nested():

            await advance_bracket_dependency(
                database,
                dependency_id,
                reason="Review corrected semifinal result",
            )

    await database.refresh(final)

    assert final.home_team_id == original_home
    assert final.away_team_id == original_away
    assert final.version == original_version
    assert final.match_id == final_match_id

    linked_match = await database.get(
        Match,
        final_match_id,
    )

    assert linked_match.team_a_id == original_home
    assert linked_match.team_b_id == original_away


# --------------------------------------------------
# Tournament finalization
# --------------------------------------------------


async def test_unfinished_tournament_cannot_be_finalized(
    database,
    competition,
):

    tournament, _, _ = await prepare_knockout(
        database,
        competition,
    )

    tournament_id = tournament.id

    with pytest.raises(ConflictError):

        async with database.begin_nested():

            await finalize_tournament(
                database,
                tournament_id,
                actor_id="integration-test",
            )

    count = await database.scalar(
        select(func.count(TournamentCloseout.id))
        .where(
            TournamentCloseout.tournament_id
            == tournament_id
        )
    )

    assert count == 0


async def test_finalization_persists_official_champion(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_finalizable_tournament(
            database,
            competition,
        )
    )

    tournament_id = tournament.id

    readiness = await closeout_readiness(
        database,
        tournament_id,
    )

    assert not readiness["blockers"], (
        readiness["blockers"]
    )

    closeout = await finalize_tournament(
        database,
        tournament_id,
        actor_id="integration-test",
    )

    await database.commit()

    closeout_id = closeout.id

    database.expire_all()

    stored = await database.get(
        TournamentCloseout,
        closeout_id,
    )

    assert stored is not None
    assert stored.champion_team_id == champion_id
    assert stored.revision == 1
    assert stored.is_frozen is True

    assert (
        stored.snapshot["champion_team_id"]
        == str(champion_id)
    )

    await database.refresh(tournament)

    assert (
        tournament.status
        == TournamentStatus.COMPLETED
    )

    decisions = await list_decisions(
        database,
        tournament_id,
        {"tournament_finalized"},
    )

    assert len(decisions) == 1

    assert (
        decisions[0].payload["snapshot"]
        == stored.snapshot
    )


async def test_duplicate_finalization_is_rejected(
    database,
    competition,
):

    tournament, _ = (
        await prepare_finalizable_tournament(
            database,
            competition,
        )
    )

    tournament_id = tournament.id

    await finalize_tournament(
        database,
        tournament_id,
        actor_id="integration-test",
    )

    await database.commit()

    with pytest.raises(ConflictError):

        async with database.begin_nested():

            await finalize_tournament(
                database,
                tournament_id,
                actor_id="integration-test",
            )

    count = await database.scalar(
        select(func.count(TournamentCloseout.id))
        .where(
            TournamentCloseout.tournament_id
            == tournament_id
        )
    )

    assert count == 1

    decisions = await list_decisions(
        database,
        tournament_id,
        {"tournament_finalized"},
    )

    assert len(decisions) == 1


# --------------------------------------------------
# Reopening and historical revisions
# --------------------------------------------------


async def test_reopening_preserves_history_and_increments_revision(
    database,
    competition,
):

    tournament, champion_id = (
        await prepare_finalizable_tournament(
            database,
            competition,
        )
    )

    tournament_id = tournament.id

    closeout = await finalize_tournament(
        database,
        tournament_id,
        actor_id="integration-test",
    )

    await database.commit()

    closeout_id = closeout.id

    original_snapshot = deepcopy(
        closeout.snapshot
    )

    reopened = await reopen_tournament(
        database,
        tournament_id,
        "Reopen tournament for official review",
        actor_id="integration-test",
    )

    await database.commit()

    assert reopened.id == closeout_id
    assert reopened.is_frozen is False
    assert reopened.revision == 1

    await database.refresh(tournament)

    assert tournament.status == TournamentStatus.LIVE

    publication = await publication_state(
        database,
        tournament_id,
    )

    assert publication["published"] is False

    history = await list_decisions(
        database,
        tournament_id,
        {"tournament_reopened"},
    )

    assert len(history) == 1

    assert (
        history[0].payload["previous_snapshot"]
        == original_snapshot
    )

    # Awards must be republished before refinalization.

    with pytest.raises(ConflictError):

        async with database.begin_nested():

            await finalize_tournament(
                database,
                tournament_id,
                actor_id="integration-test",
            )

    await publish_awards(
        database,
        tournament_id,
        "Republish awards after official review",
        actor_id="integration-test",
    )

    await database.commit()

    revised = await finalize_tournament(
        database,
        tournament_id,
        actor_id="integration-test",
    )

    await database.commit()

    assert revised.id == closeout_id
    assert revised.revision == 2
    assert revised.is_frozen is True
    assert revised.champion_team_id == champion_id

    history = await list_decisions(
        database,
        tournament_id,
        {"tournament_finalized"},
    )

    assert len(history) == 2

    revisions = {
        decision.payload["revision"]: decision.payload
        for decision in history
    }

    assert set(revisions) == {1, 2}

    assert (
        revisions[1]["snapshot"]
        == original_snapshot
    )

    assert (
        revisions[2]["snapshot"]
        == revised.snapshot
    )
