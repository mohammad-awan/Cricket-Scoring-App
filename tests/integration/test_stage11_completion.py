"""Stage 11 completion workflows against PostgreSQL.

Pagination, reserve promotion and replacement cutoffs, disciplinary
deductions, branding uploads, series/editions and player eligibility.
"""

from datetime import UTC, date, datetime, timedelta
import pytest
from sqlalchemy import update
from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionFactory
from app.domain.tournament_rules import TournamentRules
from app.models import Player, PlayerSex, TournamentAsset, TournamentStatus
from app.repositories.tournaments import TournamentRepository
from app.schemas.tournaments import (
    CompetitionConfigUpdate,
    PointDeductionCreate,
    TournamentSeriesCreate,
    TournamentTeamRegister,
)
from app.services import tournament_assets as asset_svc
from app.services import tournament_discipline as discipline_svc
from app.services import tournament_series as series_svc
from app.services import tournaments as svc
from app.services.storage import LocalObjectStorage
from app.services.tournament_eligibility import overseas_limit_errors
from tests.integration.stage11_support import (
    add_roster,
    build_world,
    call,
    cleanup,
    invite,
    live_db,
    small_rules,
    transition,
)


pytestmark = [pytest.mark.integration, live_db]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x02" * 64


async def set_players(player_ids, **values) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            await session.execute(
                update(Player).where(Player.id.in_(player_ids)).values(**values)
            )


@pytest.mark.asyncio
async def test_team_list_is_paginated_with_filters_and_search() -> None:
    world = await build_world(teams=5, rules=small_rules())
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        for team_id in world.team_ids:
            await invite(world, team_id)

        first = await call(svc.list_tournament_teams_page, world.tournament_id, page=1, page_size=2)
        last = await call(svc.list_tournament_teams_page, world.tournament_id, page=3, page_size=2)

        assert (first.total, first.pages, len(first.items)) == (5, 3, 2)
        assert len(last.items) == 1
        assert {item.id for item in first.items}.isdisjoint({item.id for item in last.items})

        found = await call(
            svc.list_tournament_teams_page,
            world.tournament_id,
            page=1,
            page_size=10,
            search="team 3",
        )
        assert [item.team_id for item in found.items] == [world.team_ids[3]]

        none_pending = await call(
            svc.list_tournament_teams_page,
            world.tournament_id,
            page=1,
            page_size=10,
            registration_status="pending",
        )
        assert none_pending.total == 0
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_reserve_promotion_replaces_withdrawn_team_until_cutoff() -> None:
    world = await build_world(
        teams=4,
        rules=small_rules(),
        config={"maximum_teams": 2, "reserve_team_limit": 2},
    )
    try:
        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        main_a = await invite(world, world.team_ids[0])
        await invite(world, world.team_ids[1])
        reserve_c = await invite(world, world.team_ids[2])
        reserve_d = await invite(world, world.team_ids[3])
        assert reserve_c.is_reserve and reserve_d.is_reserve

        # Main draw is full.
        with pytest.raises(ConflictError, match="full"):
            await call(svc.promote_reserve_team, world.tournament_id, reserve_c.id)

        await call(svc.withdraw_tournament_team, world.tournament_id, main_a.id, "Team folded")

        # Only withdrawn entries can be replaced.
        with pytest.raises(ConflictError, match="withdrawn"):
            await call(svc.promote_reserve_team, world.tournament_id, reserve_c.id, reserve_d.id)

        promoted = await call(
            svc.promote_reserve_team,
            world.tournament_id,
            reserve_c.id,
            main_a.id,
            "Next on the waiting list",
        )
        assert promoted.is_reserve is False
        assert promoted.replaces_membership_id == main_a.id

        with pytest.raises(ConflictError, match="already in the main draw"):
            await call(svc.promote_reserve_team, world.tournament_id, reserve_c.id)

        # A second withdrawal frees a place, but the cutoff has passed.
        await call(svc.withdraw_tournament_team, world.tournament_id, promoted.id, "Withdrew")
        await call(
            svc.configure_tournament,
            world.tournament_id,
            CompetitionConfigUpdate(replacement_cutoff_at=datetime.now(UTC) - timedelta(minutes=1)),
        )
        with pytest.raises(ConflictError, match="cutoff"):
            await call(svc.promote_reserve_team, world.tournament_id, reserve_d.id, promoted.id)

        # A withdrawal can only be replaced once.
        await call(
            svc.configure_tournament,
            world.tournament_id,
            CompetitionConfigUpdate(replacement_cutoff_at=datetime.now(UTC) + timedelta(days=1)),
        )
        with pytest.raises(ConflictError, match="already been replaced"):
            await call(svc.promote_reserve_team, world.tournament_id, reserve_d.id, main_a.id)
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_point_deductions_are_audited_and_revoked_not_deleted() -> None:
    world = await build_world(
        teams=2,
        rules=small_rules(),
        config={"entry_requires_approval": True},
    )
    try:
        payload = lambda membership_id, points=2: PointDeductionCreate(  # noqa: E731
            tournament_team_id=membership_id,
            points=points,
            reason="Slow over rate",
        )

        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        approved = await invite(world, world.team_ids[0])
        pending = await call(
            svc.register_tournament_team,
            world.tournament_id,
            TournamentTeamRegister(team_id=world.team_ids[1]),
        )
        assert pending.registration_status == "pending"

        with pytest.raises(ConflictError, match="approved"):
            await call(discipline_svc.create_point_deduction, world.tournament_id, payload(pending.id))

        deduction = await call(
            discipline_svc.create_point_deduction,
            world.tournament_id,
            payload(approved.id),
            actor_id="organizer",
        )
        assert (deduction.points, deduction.created_by) == (2, "organizer")

        revoked = await call(
            discipline_svc.revoke_point_deduction,
            world.tournament_id,
            deduction.id,
            "Appeal upheld",
        )
        again = await call(
            discipline_svc.revoke_point_deduction,
            world.tournament_id,
            deduction.id,
            "Duplicate click",
        )
        assert revoked.revoked_reason == again.revoked_reason == "Appeal upheld"

        everything = await call(discipline_svc.list_point_deductions, world.tournament_id)
        active = await call(discipline_svc.list_point_deductions, world.tournament_id, False)
        assert [item.id for item in everything] == [deduction.id]
        assert active == []

        events = {item.event_type for item in await call(svc.list_tournament_audit, world.tournament_id, 50)}
        assert {"points_deducted", "point_deduction_revoked"} <= events
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_draft_tournaments_cannot_deduct_points() -> None:
    world = await build_world(teams=2, rules=small_rules())
    try:
        membership = await invite(world, world.team_ids[0])
        with pytest.raises(ConflictError, match="draft"):
            await call(
                discipline_svc.create_point_deduction,
                world.tournament_id,
                PointDeductionCreate(tournament_team_id=membership.id, points=1, reason="Too early"),
            )
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_branding_upload_replace_and_remove(tmp_path) -> None:
    world = await build_world(teams=2)
    storage = LocalObjectStorage(tmp_path)
    try:
        logo = await call(
            asset_svc.upload_tournament_asset,
            world.tournament_id,
            "logo",
            PNG,
            declared_type="image/png",
            filename="C:\\fakepath\\logo.png",
            storage=storage,
        )
        same = await call(
            asset_svc.upload_tournament_asset,
            world.tournament_id,
            "logo",
            PNG,
            storage=storage,
        )
        assert same.id == logo.id
        assert logo.original_filename == "logo.png"
        assert logo.url.startswith(f"/tournaments/{world.tournament_id}/assets/logo?v=")

        replaced = await call(
            asset_svc.upload_tournament_asset,
            world.tournament_id,
            "logo",
            JPEG,
            storage=storage,
        )
        assert replaced.content_type == "image/jpeg"

        current = await call(asset_svc.list_tournament_assets, world.tournament_id)
        assert [item.id for item in current] == [replaced.id]

        path, asset = await call(
            asset_svc.current_asset_file,
            world.tournament_id,
            "logo",
            storage,
        )
        assert path.read_bytes() == JPEG and asset.id == replaced.id

        # History is kept: the first upload is no longer current.
        async with AsyncSessionFactory() as session:
            old = await session.get(TournamentAsset, logo.id)
            assert old.is_current is False

        assert await call(asset_svc.clear_tournament_asset, world.tournament_id, "logo") == {"removed": True}
        assert await call(asset_svc.list_tournament_assets, world.tournament_id) == []
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_series_links_editions() -> None:
    world = await build_world(teams=2)
    try:
        series = await call(
            series_svc.create_tournament_series,
            TournamentSeriesCreate(name=f"S11 Series {world.suffix}"),
        )
        world.series_ids.append(series.id)

        with pytest.raises(ConflictError):
            await call(
                series_svc.create_tournament_series,
                TournamentSeriesCreate(name=f"S11 Series {world.suffix}".upper()),
            )

        configured = await call(
            svc.configure_tournament,
            world.tournament_id,
            CompetitionConfigUpdate(series_id=series.id, edition_number=3),
        )
        assert (configured.series_id, configured.edition_number) == (series.id, 3)

        editions = await call(series_svc.list_series_editions, series.id)
        assert [item.id for item in editions] == [world.tournament_id]
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_roster_eligibility_by_age_and_sex() -> None:
    rules = small_rules(eligibility={"maximum_age": 19, "sex": "female"})
    world = await build_world(teams=2, players_per_team=4, rules=rules)
    squad = world.players[world.team_ids[0]]
    try:
        await set_players(squad, date_of_birth=date(2010, 1, 1), sex=PlayerSex.FEMALE)
        await set_players([squad[1]], date_of_birth=date(2000, 1, 1))
        await set_players([squad[2]], sex=PlayerSex.MALE)
        await set_players([squad[3]], sex=None)

        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        membership = await invite(world, world.team_ids[0])

        candidates = {
            item.player_id: item
            for item in await call(svc.list_roster_candidates, world.tournament_id, membership.id)
        }
        assert candidates[squad[0]].eligible
        assert any("maximum age" in reason for reason in candidates[squad[1]].reasons)
        assert any("female-only" in reason for reason in candidates[squad[2]].reasons)
        assert any("no recorded sex" in reason for reason in candidates[squad[3]].reasons)

        await add_roster(world, membership.id, squad[0])
        remaining = await call(svc.list_roster_candidates, world.tournament_id, membership.id)
        assert squad[0] not in {item.player_id for item in remaining}

        with pytest.raises(ValidationError, match="maximum age"):
            await add_roster(world, membership.id, squad[1])
        with pytest.raises(ValidationError, match="female-only"):
            await add_roster(world, membership.id, squad[2])
        with pytest.raises(ValidationError, match="no recorded sex"):
            await add_roster(world, membership.id, squad[3])

        # A player record changed after rostering is caught by readiness.
        await set_players([squad[0]], sex=PlayerSex.MALE)
        readiness = await call(svc.validate_tournament_readiness, world.tournament_id)
        assert any("female-only" in error for error in readiness["errors"])
    finally:
        await cleanup(world)


@pytest.mark.asyncio
async def test_overseas_limit_needs_nationality_and_caps_the_xi() -> None:
    rules = small_rules(overseas_player_limit=1, eligibility={"home_nationality": "Pakistan"})
    world = await build_world(teams=2, players_per_team=3, rules=rules)
    squad = world.players[world.team_ids[0]]
    try:
        await set_players(squad, nationality="England")
        await set_players([squad[2]], nationality=None)

        await transition(world, TournamentStatus.REGISTRATION_OPEN)
        membership = await invite(world, world.team_ids[0])

        await add_roster(world, membership.id, squad[0])
        with pytest.raises(ValidationError, match="nationality"):
            await add_roster(world, membership.id, squad[2])

        async with AsyncSessionFactory() as session:
            repository = TournamentRepository(session)
            parsed = TournamentRules.model_validate(rules.model_dump(mode="json"))
            assert await overseas_limit_errors(
                repository, parsed, team_label="Team A", player_ids=squad[:1]
            ) == []
            assert await overseas_limit_errors(
                repository, parsed, team_label="Team A", player_ids=squad[:2]
            )
    finally:
        await cleanup(world)
