from __future__ import annotations
from uuid import UUID
from sqlalchemy import func, or_, select
from app.models import (
    Match,
    MatchPlayer,
    MatchStatus,
    Player,
    Team,
    Tournament,
    TournamentAsset,
    TournamentAuditEvent,
    TournamentGroup,
    TournamentPointDeduction,
    TournamentRoster,
    TournamentRuleSet,
    TournamentSeries,
    TournamentTeam,
    TournamentVenue,
)
from app.repositories.base_master_data import MasterDataRepository


# Registrations that still occupy a place in the competition.
ACTIVE_REGISTRATION_STATUSES = ("pending", "approved")


class TournamentRepository(MasterDataRepository[Tournament]):
    model = Tournament
    search_fields = (
        Tournament.name,
        Tournament.slug,
        Tournament.season,
        Tournament.organizer,
    )

    async def find_duplicate(
        self,
        *,
        name: str,
        season: str | None,
        slug: str,
        exclude_id: UUID | None = None,
    ) -> str | None:
        if await self.exists(
            Tournament.slug == slug,
            exclude_id=exclude_id,
        ):
            return "slug"

        season_condition = (
            Tournament.season.is_(None)
            if season is None
            else Tournament.season == season
        )

        if await self.exists(
            func.lower(Tournament.name) == name.lower(),
            season_condition,
            exclude_id=exclude_id,
        ):
            return "name/season"

        return None

    # Tournament row

    async def get_locked(self, tournament_id: UUID) -> Tournament | None:
        return await self.session.scalar(
            select(Tournament)
            .where(Tournament.id == tournament_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    # Rule versions

    async def latest_rules(self, tournament_id: UUID) -> TournamentRuleSet | None:
        return await self.session.scalar(
            select(TournamentRuleSet)
            .where(TournamentRuleSet.tournament_id == tournament_id)
            .order_by(TournamentRuleSet.version.desc())
            .limit(1)
        )

    async def get_rule_version(
        self,
        tournament_id: UUID,
        version: int,
    ) -> TournamentRuleSet | None:
        return await self.session.scalar(
            select(TournamentRuleSet).where(
                TournamentRuleSet.tournament_id == tournament_id,
                TournamentRuleSet.version == version,
            )
        )

    async def list_rule_versions(self, tournament_id: UUID) -> list[TournamentRuleSet]:
        result = await self.session.scalars(
            select(TournamentRuleSet)
            .where(TournamentRuleSet.tournament_id == tournament_id)
            .order_by(TournamentRuleSet.version.desc())
        )
        return list(result.all())

    # Registrations

    async def get_registration(
        self,
        tournament_id: UUID,
        team_id: UUID,
    ) -> TournamentTeam | None:
        return await self.session.scalar(
            select(TournamentTeam).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.team_id == team_id,
            )
        )

    async def get_membership(
        self,
        tournament_id: UUID,
        membership_id: UUID,
    ) -> TournamentTeam | None:
        return await self.session.scalar(
            select(TournamentTeam).where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.id == membership_id,
            )
        )

    async def list_registrations(
        self,
        tournament_id: UUID,
        *,
        registration_status: str | None = None,
    ) -> list[TournamentTeam]:
        statement = select(TournamentTeam).where(
            TournamentTeam.tournament_id == tournament_id
        )
        if registration_status is not None:
            statement = statement.where(
                TournamentTeam.registration_status == registration_status
            )

        result = await self.session.scalars(
            statement.order_by(
                TournamentTeam.seed.asc().nulls_last(),
                TournamentTeam.created_at,
            )
        )
        return list(result.all())

    async def page_registrations(
        self,
        tournament_id: UUID,
        *,
        page: int,
        page_size: int,
        registration_status: str | None = None,
        is_reserve: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[TournamentTeam], int]:
        conditions = [TournamentTeam.tournament_id == tournament_id]

        if registration_status is not None:
            conditions.append(TournamentTeam.registration_status == registration_status)

        if is_reserve is not None:
            conditions.append(TournamentTeam.is_reserve.is_(is_reserve))

        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(func.coalesce(TournamentTeam.display_name, "")).like(pattern),
                    func.lower(Team.name).like(pattern),
                    func.lower(func.coalesce(Team.short_name, "")).like(pattern),
                    func.lower(func.coalesce(TournamentTeam.manager_name, "")).like(pattern),
                )
            )

        base = (
            select(TournamentTeam)
            .join(Team, Team.id == TournamentTeam.team_id)
            .where(*conditions)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(base.subquery())
            )
            or 0
        )
        result = await self.session.scalars(
            base.order_by(
                TournamentTeam.seed.asc().nulls_last(),
                TournamentTeam.created_at,
                TournamentTeam.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.all()), total

    async def get_membership_locked(
        self,
        tournament_id: UUID,
        membership_id: UUID,
    ) -> TournamentTeam | None:
        return await self.session.scalar(
            select(TournamentTeam)
            .where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.id == membership_id,
            )
            .with_for_update()
        )

    async def get_replacement_for(self, membership_id: UUID) -> TournamentTeam | None:
        return await self.session.scalar(
            select(TournamentTeam).where(
                TournamentTeam.replaces_membership_id == membership_id
            )
        )

    async def count_registrations(
        self,
        tournament_id: UUID,
        *,
        approved_only: bool = False,
        is_reserve: bool | None = None,
    ) -> int:
        statuses = ("approved",) if approved_only else ACTIVE_REGISTRATION_STATUSES
        statement = select(func.count(TournamentTeam.id)).where(
            TournamentTeam.tournament_id == tournament_id,
            TournamentTeam.registration_status.in_(statuses),
        )
        if is_reserve is not None:
            statement = statement.where(TournamentTeam.is_reserve.is_(is_reserve))

        return int(await self.session.scalar(statement) or 0)

    async def approved_team_ids(
        self,
        tournament_id: UUID,
        *,
        include_reserve: bool = False,
    ) -> set[UUID]:
        statement = select(TournamentTeam.team_id).where(
            TournamentTeam.tournament_id == tournament_id,
            TournamentTeam.registration_status == "approved",
        )
        if not include_reserve:
            statement = statement.where(TournamentTeam.is_reserve.is_(False))

        result = await self.session.scalars(statement)
        return set(result.all())

    # Rosters

    async def get_roster_player(
        self,
        membership_id: UUID,
        player_id: UUID,
    ) -> TournamentRoster | None:
        return await self.session.scalar(
            select(TournamentRoster).where(
                TournamentRoster.tournament_team_id == membership_id,
                TournamentRoster.player_id == player_id,
            )
        )

    async def list_roster(self, membership_id: UUID) -> list[TournamentRoster]:
        result = await self.session.scalars(
            select(TournamentRoster)
            .where(TournamentRoster.tournament_team_id == membership_id)
            .order_by(TournamentRoster.created_at)
        )
        return list(result.all())

    async def player_registered_elsewhere(
        self,
        tournament_id: UUID,
        player_id: UUID,
        *,
        exclude_membership_id: UUID,
    ) -> bool:
        """True when the player is on another active team roster
        in the same tournament."""

        statement = (
            select(TournamentRoster.id)
            .join(
                TournamentTeam,
                TournamentRoster.tournament_team_id == TournamentTeam.id,
            )
            .where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.id != exclude_membership_id,
                TournamentTeam.registration_status.in_(
                    ACTIVE_REGISTRATION_STATUSES
                ),
                TournamentRoster.player_id == player_id,
            )
            .limit(1)
        )
        return await self.session.scalar(statement) is not None

    async def players_on_other_rosters(
        self,
        tournament_id: UUID,
        *,
        exclude_membership_id: UUID,
    ) -> set[UUID]:
        """Players already on another active team roster in the tournament."""

        result = await self.session.scalars(
            select(TournamentRoster.player_id)
            .join(
                TournamentTeam,
                TournamentRoster.tournament_team_id == TournamentTeam.id,
            )
            .where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.id != exclude_membership_id,
                TournamentTeam.registration_status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
        return set(result.all())

    async def available_roster_player_ids(
        self,
        tournament_id: UUID,
        team_id: UUID,
    ) -> set[UUID]:
        result = await self.session.scalars(
            select(TournamentRoster.player_id)
            .join(
                TournamentTeam,
                TournamentRoster.tournament_team_id == TournamentTeam.id,
            )
            .where(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.team_id == team_id,
                TournamentTeam.registration_status == "approved",
                TournamentRoster.is_available.is_(True),
            )
        )
        return set(result.all())

    # Groups

    async def get_group(
        self,
        tournament_id: UUID,
        group_id: UUID,
    ) -> TournamentGroup | None:
        return await self.session.scalar(
            select(TournamentGroup).where(
                TournamentGroup.tournament_id == tournament_id,
                TournamentGroup.id == group_id,
            )
        )

    async def get_group_by_name(
        self,
        tournament_id: UUID,
        name: str,
    ) -> TournamentGroup | None:
        return await self.session.scalar(
            select(TournamentGroup).where(
                TournamentGroup.tournament_id == tournament_id,
                TournamentGroup.name == name,
            )
        )

    async def list_groups(self, tournament_id: UUID) -> list[TournamentGroup]:
        result = await self.session.scalars(
            select(TournamentGroup)
            .where(TournamentGroup.tournament_id == tournament_id)
            .order_by(TournamentGroup.sort_order, TournamentGroup.name)
        )
        return list(result.all())

    async def count_group_members(self, group_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count(TournamentTeam.id)).where(
                    TournamentTeam.group_id == group_id,
                    TournamentTeam.registration_status.in_(
                        ACTIVE_REGISTRATION_STATUSES
                    ),
                )
            )
            or 0
        )

    # Venues

    async def venue_allowed(self, tournament_id: UUID, venue_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(TournamentVenue.id).where(
                    TournamentVenue.tournament_id == tournament_id,
                    TournamentVenue.venue_id == venue_id,
                )
            )
            is not None
        )

    async def get_venue_link(
        self,
        tournament_id: UUID,
        venue_id: UUID,
    ) -> TournamentVenue | None:
        return await self.session.scalar(
            select(TournamentVenue).where(
                TournamentVenue.tournament_id == tournament_id,
                TournamentVenue.venue_id == venue_id,
            )
        )

    async def list_venues(self, tournament_id: UUID) -> list[TournamentVenue]:
        result = await self.session.scalars(
            select(TournamentVenue).where(
                TournamentVenue.tournament_id == tournament_id
            )
        )
        return list(result.all())

    # Matches

    async def tournament_match_uses_venue(
        self,
        tournament_id: UUID,
        venue_id: UUID,
    ) -> bool:
        return (
            await self.session.scalar(
                select(Match.id)
                .where(
                    Match.tournament_id == tournament_id,
                    Match.venue_id == venue_id,
                )
                .limit(1)
            )
            is not None
        )

    async def team_has_matches(self, tournament_id: UUID, team_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(Match.id)
                .where(
                    Match.tournament_id == tournament_id,
                    or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
                    Match.status != MatchStatus.ABANDONED,
                )
                .limit(1)
            )
            is not None
        )

    async def match_has_selections(self, match_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(MatchPlayer.id).where(MatchPlayer.match_id == match_id).limit(1)
            )
            is not None
        )

    async def list_matches(
        self,
        tournament_id: UUID,
        *,
        statuses: tuple[MatchStatus, ...] | None = None,
        for_update: bool = False,
    ) -> list[Match]:
        statement = select(Match).where(Match.tournament_id == tournament_id)
        if statuses is not None:
            statement = statement.where(Match.status.in_(statuses))
        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(statement.order_by(Match.created_at))
        return list(result.all())

    async def count_matches(
        self,
        tournament_id: UUID,
        *,
        statuses: tuple[MatchStatus, ...] | None = None,
    ) -> int:
        statement = select(func.count(Match.id)).where(
            Match.tournament_id == tournament_id
        )
        if statuses is not None:
            statement = statement.where(Match.status.in_(statuses))

        return int(await self.session.scalar(statement) or 0)

    # Audit

    async def list_audit_events(
        self,
        tournament_id: UUID,
        *,
        limit: int = 100,
    ) -> list[TournamentAuditEvent]:
        result = await self.session.scalars(
            select(TournamentAuditEvent)
            .where(TournamentAuditEvent.tournament_id == tournament_id)
            .order_by(TournamentAuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    # Players (eligibility)

    async def players_by_ids(self, player_ids: set[UUID]) -> dict[UUID, Player]:
        if not player_ids:
            return {}

        result = await self.session.scalars(
            select(Player).where(Player.id.in_(player_ids))
        )
        return {player.id: player for player in result.all()}

    # Point deductions

    async def list_deductions(
        self,
        tournament_id: UUID,
        *,
        include_revoked: bool = True,
    ) -> list[TournamentPointDeduction]:
        statement = select(TournamentPointDeduction).where(
            TournamentPointDeduction.tournament_id == tournament_id
        )
        if not include_revoked:
            statement = statement.where(TournamentPointDeduction.revoked_at.is_(None))

        result = await self.session.scalars(
            statement.order_by(TournamentPointDeduction.created_at.desc())
        )
        return list(result.all())

    async def get_deduction_locked(
        self,
        tournament_id: UUID,
        deduction_id: UUID,
    ) -> TournamentPointDeduction | None:
        return await self.session.scalar(
            select(TournamentPointDeduction)
            .where(
                TournamentPointDeduction.tournament_id == tournament_id,
                TournamentPointDeduction.id == deduction_id,
            )
            .with_for_update()
        )

    # Branding assets

    async def current_assets(self, tournament_id: UUID) -> list[TournamentAsset]:
        result = await self.session.scalars(
            select(TournamentAsset)
            .where(
                TournamentAsset.tournament_id == tournament_id,
                TournamentAsset.is_current.is_(True),
            )
            .order_by(TournamentAsset.kind)
        )
        return list(result.all())

    async def current_asset(self, tournament_id: UUID, kind: str) -> TournamentAsset | None:
        return await self.session.scalar(
            select(TournamentAsset).where(
                TournamentAsset.tournament_id == tournament_id,
                TournamentAsset.kind == kind,
                TournamentAsset.is_current.is_(True),
            )
        )

    async def asset_by_key(self, object_key: str) -> TournamentAsset | None:
        return await self.session.scalar(
            select(TournamentAsset).where(TournamentAsset.object_key == object_key)
        )

    # Series

    async def list_editions(self, series_id: UUID) -> list[Tournament]:
        result = await self.session.scalars(
            select(Tournament)
            .where(Tournament.series_id == series_id)
            .order_by(
                Tournament.edition_number.asc().nulls_last(),
                Tournament.start_date.asc().nulls_last(),
                Tournament.created_at,
            )
        )
        return list(result.all())


class TournamentSeriesRepository(MasterDataRepository[TournamentSeries]):
    model = TournamentSeries
    search_fields = (
        TournamentSeries.name,
        TournamentSeries.slug,
        TournamentSeries.organizer,
    )

    def build_conditions(self, *, search: str | None = None, include_archived: bool = False) -> list:
        # Series have no archive lifecycle; only search narrows the list.
        return super().build_conditions(search=search, include_archived=True)
