from __future__ import annotations
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.tournament_rules import (
    TournamentRules,
    checksum_rules,
    match_config_from_rules,
    scoring_capability_errors,
)
from app.models import (
    AuditAction,
    MatchStatus,
    Player,
    PlayerStatus,
    Team,
    TeamStatus,
    Tournament,
    TournamentAuditEvent,
    TournamentGroup,
    TournamentRoster,
    TournamentRuleSet,
    TournamentSeries,
    TournamentStatus,
    TournamentTeam,
    TournamentVenue,
    Venue,
    VenueStatus,
)
from app.repositories.match_setup import MatchSetupRepository
from app.repositories.tournaments import TournamentRepository
from app.schemas.common import MasterDataQuery, PageResponse
from app.schemas.tournaments import (
    CompetitionConfig,
    CompetitionConfigUpdate,
    RosterAdd,
    RosterCandidateRead,
    RulePropagationRequest,
    RuleVersionCreate,
    TournamentCreate,
    TournamentRead,
    TournamentTeamRead,
    TournamentTeamRegister,
    TournamentUpdate,
)
from app.services.common import (
    add_audit_log,
    duplicate_conflict,
    integrity_conflict,
    list_master_data,
    service_transaction,
)
from app.services.tournament_eligibility import (
    player_errors,
    players_eligibility_errors,
)
from app.utils.text import clean_optional, clean_required, slugify


def tournament_slug(
    name: str,
    season: str | None,
    supplied_slug: str | None,
) -> str:
    try:
        if supplied_slug:
            return slugify(supplied_slug)

        value = f"{name}-{season}" if season else name
        return slugify(value)

    except ValueError as error:
        raise ValidationError(
            "The tournament slug must contain letters or numbers"
        ) from error


async def create_tournament(session: AsyncSession, payload: TournamentCreate) -> Tournament:
    repository = TournamentRepository(session)
    name = clean_required(payload.name)
    season = clean_optional(payload.season)
    slug = tournament_slug(
        name,
        season,
        clean_optional(payload.slug),
    )

    try:
        async with service_transaction(session):
            duplicate = await repository.find_duplicate(
                name=name,
                season=season,
                slug=slug,
            )

            if duplicate:
                raise duplicate_conflict(
                    "tournament",
                    duplicate,
                )

            tournament = repository.add(
                Tournament(
                    name=name,
                    slug=slug,
                    season=season,
                    organizer=clean_optional(
                        payload.organizer
                    ),
                    description=clean_optional(
                        payload.description
                    ),
                    start_date=payload.start_date,
                    end_date=payload.end_date,
                )
            )

            await repository.flush_refresh(tournament)

            add_audit_log(
                session,
                entity_type="tournament",
                entity_id=tournament.id,
                action=AuditAction.CREATED,
                details={
                    "fields": [
                        "name",
                        "slug",
                        "season",
                        "start_date",
                        "end_date",
                    ]
                },
            )

            await session.flush()
            return tournament

    except IntegrityError as error:
        raise integrity_conflict(
            error,
            "Tournament",
        ) from error


async def list_tournaments(session: AsyncSession, query: MasterDataQuery) -> PageResponse[TournamentRead]:
    return await list_master_data(TournamentRepository(session), query, TournamentRead)


async def get_tournament(session: AsyncSession, tournament_id: UUID) -> Tournament:
    tournament = await TournamentRepository(session).get_by_id(tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    return tournament



# Tournament identity and scheduling safeguards.

IDENTITY_LOCKED_STATUSES = frozenset({
    TournamentStatus.SCHEDULED,
    TournamentStatus.LIVE,
    TournamentStatus.COMPLETED,
    TournamentStatus.SUSPENDED,
    TournamentStatus.CANCELLED,
    TournamentStatus.ARCHIVED,
})

IDENTITY_LOCKED_FIELDS = frozenset({
    "name",
    "slug",
    "season",
    "start_date",
    "end_date",
})

TERMINAL_TOURNAMENT_STATUSES = frozenset({
    TournamentStatus.COMPLETED,
    TournamentStatus.CANCELLED,
    TournamentStatus.ARCHIVED,
})


def validate_tournament_identity_update(tournament: Tournament, changes: dict[str, Any]) -> None:
    """Reject identity or schedule changes after scheduling.

    Ordinary editable descriptive metadata can remain changeable.
    Rule changes must go through versioned rule-set services.
    """
    if tournament.status == TournamentStatus.ARCHIVED:
        raise ConflictError("Archived tournaments cannot be updated")

    if tournament.status in TERMINAL_TOURNAMENT_STATUSES:
        raise ConflictError("Completed or cancelled tournaments are read-only")

    if tournament.status in IDENTITY_LOCKED_STATUSES:
        changed_fields = {
            field
            for field in IDENTITY_LOCKED_FIELDS.intersection(changes)
            if changes[field] != getattr(tournament, field)
        }

        if changed_fields:
            raise ConflictError("Tournament identity or schedule is locked: " + ", ".join(sorted(changed_fields)))


async def update_tournament(session: AsyncSession, tournament_id: UUID, payload: TournamentUpdate) -> Tournament:
    repository = TournamentRepository(session)
    data = payload.model_dump(exclude_unset=True)

    try:
        async with service_transaction(session):
            tournament = await repository.get_by_id(tournament_id)
            if tournament is None:
                raise NotFoundError("Tournament not found")
 
            validate_tournament_identity_update(tournament, data)

            name = clean_required(data.get("name", tournament.name))
            season = clean_optional(data.get("season", tournament.season))
            slug = tournament.slug

            if "slug" in data:
                slug = tournament_slug(
                    name,
                    season,
                    clean_optional(data["slug"]),
                )

            start_date = data.get("start_date", tournament.start_date)
            end_date = data.get("end_date", tournament.end_date)

            if (
                start_date
                and end_date
                and end_date < start_date
            ):
                raise ValidationError(
                    "end_date must be on or after start_date"
                )

            duplicate = await repository.find_duplicate(
                name=name,
                season=season,
                slug=slug,
                exclude_id=tournament.id,
            )

            if duplicate:
                raise duplicate_conflict("tournament", duplicate)

            if "name" in data:
                tournament.name = name

            if "slug" in data:
                tournament.slug = slug

            if "season" in data:
                tournament.season = season

            if "organizer" in data:
                tournament.organizer = clean_optional(data["organizer"])

            if "description" in data:
                tournament.description = clean_optional(data["description"])

            if "start_date" in data:
                tournament.start_date = start_date

            if "end_date" in data:
                tournament.end_date = end_date

            tournament.updated_at = datetime.now(UTC)

            await repository.flush_refresh(tournament)

            add_audit_log(
                session,
                entity_type="tournament",
                entity_id=tournament.id,
                action=AuditAction.UPDATED,
                details={"fields": sorted(data)},
            )

            await session.flush()
            return tournament

    except IntegrityError as error:
        raise integrity_conflict(
            error,
            "Tournament",
        ) from error




# ---------------------------------------------------------------------------
# Stage 11: governed tournament competition
# ---------------------------------------------------------------------------

TOURNAMENT_TRANSITIONS: dict[TournamentStatus, set[TournamentStatus]] = {
    TournamentStatus.DRAFT: {
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.CANCELLED,
    },
    TournamentStatus.REGISTRATION_OPEN: {
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.SUSPENDED,
        TournamentStatus.CANCELLED,
    },
    TournamentStatus.REGISTRATION_CLOSED: {
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.SCHEDULED,
        TournamentStatus.SUSPENDED,
        TournamentStatus.CANCELLED,
    },
    TournamentStatus.SCHEDULED: {
        TournamentStatus.LIVE,
        TournamentStatus.SUSPENDED,
        TournamentStatus.CANCELLED,
    },
    TournamentStatus.LIVE: {
        TournamentStatus.COMPLETED,
        TournamentStatus.SUSPENDED,
    },
    TournamentStatus.COMPLETED: {
        TournamentStatus.ARCHIVED,
    },
    TournamentStatus.CANCELLED: {
        TournamentStatus.ARCHIVED,
    },
    TournamentStatus.SUSPENDED: {
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
        TournamentStatus.CANCELLED,
    },
    # Legacy pre-Stage 11 status.
    TournamentStatus.ACTIVE: {
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
        TournamentStatus.COMPLETED,
    },
    TournamentStatus.ARCHIVED: set(),
}

# Statuses that existed before Stage 11. A tournament in one of these
# states with no rule version is a legacy record and keeps the original
# direct-archive behaviour.
LEGACY_STATUSES = frozenset(
    {
        TournamentStatus.DRAFT,
        TournamentStatus.ACTIVE,
        TournamentStatus.COMPLETED,
    }
)

CONFIGURATION_LOCKED_STATUSES = frozenset(
    {
        TournamentStatus.SCHEDULED,
        TournamentStatus.LIVE,
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    }
)

FINAL_STATUSES = frozenset(
    {
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    }
)

RULES_LOCKED_STATUSES = frozenset(
    {
        TournamentStatus.LIVE,
        TournamentStatus.COMPLETED,
        TournamentStatus.CANCELLED,
        TournamentStatus.ARCHIVED,
    }
)

REASON_REQUIRED_TARGETS = frozenset(
    {
        TournamentStatus.SUSPENDED,
        TournamentStatus.CANCELLED,
    }
)

IN_PROGRESS_MATCH_STATUSES = (
    MatchStatus.LIVE,
    MatchStatus.INNINGS_BREAK,
)

UNFINISHED_MATCH_STATUSES = (
    MatchStatus.READY,
    MatchStatus.LIVE,
    MatchStatus.INNINGS_BREAK,
)

ACTIVE_REGISTRATION_STATUSES = frozenset({"pending", "approved"})


# Pure policy helpers


def transition_allowed(
    current: TournamentStatus,
    target: TournamentStatus,
) -> bool:
    return target in TOURNAMENT_TRANSITIONS.get(current, set())


def ensure_transition_allowed(
    current: TournamentStatus,
    target: TournamentStatus,
) -> None:
    if not transition_allowed(current, target):
        raise ConflictError(
            f"Tournament cannot move from {current.value} "
            f"to {target.value}"
        )


def capacity_errors(
    *,
    maximum_teams: int | None,
    reserve_team_limit: int,
    active_main: int,
    active_reserve: int,
) -> list[str]:
    errors = []

    if maximum_teams is not None and active_main > maximum_teams:
        errors.append(
            f"Maximum teams cannot be below the {active_main} "
            "teams already registered"
        )

    if active_reserve > reserve_team_limit:
        errors.append(
            f"Reserve limit cannot be below the {active_reserve} "
            "reserve teams already registered"
        )

    return errors


def validate_rules_payload(rules: TournamentRules) -> dict[str, Any]:
    errors = scoring_capability_errors(rules)
    return {"valid": not errors, "errors": errors}


def _pydantic_message(error: PydanticValidationError) -> str:
    return "; ".join(item["msg"] for item in error.errors())


# Shared helpers


@asynccontextmanager
async def tournament_transaction(
    session: AsyncSession,
    resource: str,
) -> AsyncIterator[None]:
    try:
        async with service_transaction(session):
            yield
    except IntegrityError as error:
        raise integrity_conflict(error, resource) from error


def tournament_audit(
    session: AsyncSession,
    tournament_id: UUID,
    event_type: str,
    details: dict[str, Any],
    actor_id: str | None = None,
) -> None:
    session.add(
        TournamentAuditEvent(
            tournament_id=tournament_id,
            event_type=event_type,
            details=details,
            actor_id=actor_id,
        )
    )


async def locked_tournament(
    repository: TournamentRepository,
    tournament_id: UUID,
) -> Tournament:
    tournament = await repository.get_locked(tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    return tournament


def ensure_configuration_editable(tournament: Tournament) -> None:
    if tournament.status in CONFIGURATION_LOCKED_STATUSES:
        raise ConflictError(
            "Tournament configuration is locked "
            "in its current state"
        )


def ensure_roster_editable(tournament: Tournament) -> None:
    ensure_configuration_editable(tournament)

    if (
        tournament.roster_lock_at is not None
        and datetime.now(UTC) >= tournament.roster_lock_at
    ):
        raise ConflictError("Tournament roster lock deadline has passed")


def ensure_not_final(tournament: Tournament) -> None:
    if tournament.status in FINAL_STATUSES:
        raise ConflictError(
            "Tournament is closed and can no longer be changed"
        )


async def require_membership(
    repository: TournamentRepository,
    tournament_id: UUID,
    membership_id: UUID,
) -> TournamentTeam:
    membership = await repository.get_membership(tournament_id, membership_id)
    if membership is None:
        raise NotFoundError("Tournament team not found")

    return membership


async def require_active_venue(session: AsyncSession, venue_id: UUID) -> Venue:
    venue = await session.get(Venue, venue_id)
    if venue is None:
        raise NotFoundError("Venue not found")

    if venue.status != VenueStatus.ACTIVE or venue.archived_at is not None:
        raise ConflictError("Venue must be active")

    return venue


async def _refreshed(session: AsyncSession, entity: Any) -> Any:
    await session.flush()
    await session.refresh(entity)
    return entity


# Lifecycle


async def archive_tournament(session: AsyncSession, tournament_id: UUID) -> Tournament:
    """Archive a tournament.

    Governed (Stage 11) tournaments must follow the lifecycle, so they
    can only be archived once completed or cancelled. Legacy records
    (pre-Stage 11 status and no rule versions) keep direct archival.
    """

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status == TournamentStatus.ARCHIVED:
            return tournament

        governed = (
            tournament.status not in LEGACY_STATUSES
            or await repository.latest_rules(tournament_id) is not None
        )

        if governed:
            return await change_tournament_status(
                session,
                tournament_id,
                TournamentStatus.ARCHIVED,
            )

        now = datetime.now(UTC)
        tournament.status = TournamentStatus.ARCHIVED
        tournament.archived_at = now
        tournament.updated_at = now

        await repository.flush_refresh(tournament)

        add_audit_log(
            session,
            entity_type="tournament",
            entity_id=tournament.id,
            action=AuditAction.ARCHIVED,
            details={"policy": "legacy_direct_archive"},
        )

        await session.flush()
        return tournament


async def _check_transition_guards(
    session: AsyncSession,
    repository: TournamentRepository,
    tournament: Tournament,
    target: TournamentStatus,
) -> None:
    if target == TournamentStatus.REGISTRATION_OPEN:
        errors = await publication_errors(repository, tournament.id)
        if errors:
            raise ValidationError("; ".join(errors))

    if target in {TournamentStatus.SCHEDULED, TournamentStatus.LIVE}:
        preview = await validate_tournament_readiness(session, tournament.id)
        errors = list(preview["errors"])

        pending = await repository.list_registrations(
            tournament.id,
            registration_status="pending",
        )
        if pending:
            errors.append(
                "Pending registrations must be approved or rejected"
            )

        if errors:
            raise ValidationError("; ".join(errors))

    if target == TournamentStatus.COMPLETED:
        if await repository.count_matches(
            tournament.id,
            statuses=UNFINISHED_MATCH_STATUSES,
        ):
            raise ConflictError(
                "Tournament matches are still ready or in progress"
            )

    if target == TournamentStatus.CANCELLED:
        if await repository.count_matches(
            tournament.id,
            statuses=IN_PROGRESS_MATCH_STATUSES,
        ):
            raise ConflictError(
                "Cannot cancel while a tournament match is live"
            )


async def change_tournament_status(
    session: AsyncSession,
    tournament_id: UUID,
    target: TournamentStatus,
    reason: str | None = None,
    *,
    actor_id: str | None = None,
) -> Tournament:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament status"):
        tournament = await locked_tournament(repository, tournament_id)
        current = tournament.status

        if current == target:
            return tournament

        ensure_transition_allowed(current, target)

        if target in REASON_REQUIRED_TARGETS and not (reason and reason.strip()):
            raise ValidationError(
                f"A reason is required to move a tournament to {target.value}"
            )

        await _check_transition_guards(session, repository, tournament, target)

        now = datetime.now(UTC)

        if target == TournamentStatus.SCHEDULED:
            await _lock_rosters(repository, tournament, now)

        tournament.status = target
        tournament.updated_at = now

        if target == TournamentStatus.ARCHIVED:
            tournament.archived_at = now

        tournament_audit(
            session,
            tournament_id,
            "status_changed",
            {
                "from": current.value,
                "to": target.value,
                "reason": reason,
            },
            actor_id=actor_id,
        )
        add_audit_log(
            session,
            entity_type="tournament",
            entity_id=tournament.id,
            action=(
                AuditAction.ARCHIVED
                if target == TournamentStatus.ARCHIVED
                else AuditAction.UPDATED
            ),
            details={"transition": f"{current.value}_to_{target.value}"},
        )

        await repository.flush_refresh(tournament)
        return tournament


# Configuration


async def configure_tournament(
    session: AsyncSession,
    tournament_id: UUID,
    payload: CompetitionConfigUpdate,
    *,
    actor_id: str | None = None,
) -> Tournament:
    repository = TournamentRepository(session)
    updates = payload.model_dump(exclude_unset=True)

    async with tournament_transaction(session, "Tournament configuration"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        # Validate the complete merged configuration, not just the
        # fields supplied in this PATCH.
        merged = {
            field: getattr(tournament, field)
            for field in CompetitionConfig.model_fields
        }
        merged.update(updates)

        try:
            CompetitionConfig.model_validate(merged)
        except PydanticValidationError as error:
            raise ValidationError(_pydantic_message(error)) from error

        errors = capacity_errors(
            maximum_teams=merged["maximum_teams"],
            reserve_team_limit=merged["reserve_team_limit"],
            active_main=await repository.count_registrations(
                tournament_id,
                is_reserve=False,
            ),
            active_reserve=await repository.count_registrations(
                tournament_id,
                is_reserve=True,
            ),
        )
        if errors:
            raise ConflictError("; ".join(errors))

        series_id = updates.get("series_id")
        if series_id is not None and await session.get(TournamentSeries, series_id) is None:
            raise NotFoundError("Tournament series not found")

        venue_id = updates.get("primary_venue_id")
        if venue_id is not None:
            await require_active_venue(session, venue_id)

            if not await repository.venue_allowed(tournament_id, venue_id):
                session.add(
                    TournamentVenue(
                        tournament_id=tournament_id,
                        venue_id=venue_id,
                    )
                )

        for key, value in updates.items():
            setattr(tournament, key, value)

        tournament.updated_at = datetime.now(UTC)

        tournament_audit(
            session,
            tournament_id,
            "configuration_updated",
            {"fields": sorted(updates)},
            actor_id=actor_id,
        )

        await repository.flush_refresh(tournament)
        return tournament


# Immutable rule versions


async def create_tournament_rules(
    session: AsyncSession,
    tournament_id: UUID,
    payload: RuleVersionCreate,
    *,
    actor_id: str | None = None,
) -> TournamentRuleSet:
    repository = TournamentRepository(session)
    actor = actor_id or payload.created_by

    async with tournament_transaction(session, "Tournament rule version"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status in RULES_LOCKED_STATUSES:
            raise ConflictError("Rule revisions are locked")

        previous = await repository.latest_rules(tournament_id)
        rules = payload.rules
        checksum = checksum_rules(rules)

        if previous is not None and previous.checksum == checksum:
            return previous

        next_version = previous.version + 1 if previous is not None else 1

        item = TournamentRuleSet(
            tournament_id=tournament_id,
            version=next_version,
            format_code=rules.format_code,
            competition_structure=rules.structure,
            rules=rules.model_dump(mode="json"),
            checksum=checksum,
            created_by=actor,
        )
        session.add(item)

        tournament_audit(
            session,
            tournament_id,
            "rule_version_created",
            {"version": next_version, "checksum": checksum},
            actor_id=actor,
        )

        return await _refreshed(session, item)


async def list_tournament_rules(
    session: AsyncSession,
    tournament_id: UUID,
) -> list[TournamentRuleSet]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_rule_versions(tournament_id)


async def get_current_tournament_rules(
    session: AsyncSession,
    tournament_id: UUID,
) -> TournamentRuleSet:
    await get_tournament(session, tournament_id)
    ruleset = await TournamentRepository(session).latest_rules(tournament_id)
    if ruleset is None:
        raise NotFoundError("Tournament rules have not been configured")

    return ruleset


async def get_tournament_rule_version(
    session: AsyncSession,
    tournament_id: UUID,
    version: int,
) -> TournamentRuleSet:
    ruleset = await TournamentRepository(session).get_rule_version(
        tournament_id,
        version,
    )
    if ruleset is None:
        raise NotFoundError("Tournament rule version not found")

    return ruleset


async def propagate_tournament_rules(
    session: AsyncSession,
    tournament_id: UUID,
    payload: RulePropagationRequest,
    *,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Apply the current rule version to unstarted (draft) fixtures.

    ``expected_previous_version`` is the rule version the caller last
    saw; a mismatch means the rules changed underneath them.
    ``apply_to_unstarted=False`` is a dry run that only reports which
    fixtures would change. Matches whose rules are already locked
    (Ready/Live) are never modified.
    """

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament rule propagation"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_not_final(tournament)

        ruleset = await repository.latest_rules(tournament_id)
        if ruleset is None:
            raise ConflictError("Tournament rules have not been configured")

        if ruleset.version != payload.expected_previous_version:
            raise ConflictError(
                "Tournament rules changed; current version is "
                f"{ruleset.version}"
            )

        expected = match_config_from_rules(
            TournamentRules.model_validate(ruleset.rules)
        )
        matches = await repository.list_matches(
            tournament_id,
            statuses=(MatchStatus.DRAFT,),
            for_update=payload.apply_to_unstarted,
        )

        updated: list[UUID] = []
        skipped: list[UUID] = []
        now = datetime.now(UTC)

        for match in matches:
            changes = {
                field: value
                for field, value in expected.items()
                if getattr(match, field) != value
            }

            if not changes:
                continue

            if match.rules_locked_at is not None or (
                "players_per_side" in changes
                and await repository.match_has_selections(match.id)
            ):
                skipped.append(match.id)
                continue

            updated.append(match.id)

            if payload.apply_to_unstarted:
                for field, value in changes.items():
                    setattr(match, field, value)
                match.updated_at = now

        if payload.apply_to_unstarted and updated:
            tournament_audit(
                session,
                tournament_id,
                "rules_propagated",
                {
                    "version": ruleset.version,
                    "match_ids": [str(item) for item in updated],
                },
                actor_id=actor_id,
            )
            await session.flush()

        return {
            "rules_version": ruleset.version,
            "updated_match_ids": updated,
            "skipped_match_ids": skipped,
        }


# Readiness and publication


async def publication_errors(
    repository: TournamentRepository,
    tournament_id: UUID,
) -> list[str]:
    ruleset = await repository.latest_rules(tournament_id)
    if ruleset is None:
        return ["Tournament rules have not been configured"]

    return scoring_capability_errors(
        TournamentRules.model_validate(ruleset.rules)
    )


async def validate_tournament_readiness(
    session: AsyncSession,
    tournament_id: UUID,
) -> dict[str, Any]:
    repository = TournamentRepository(session)
    tournament = await get_tournament(session, tournament_id)

    errors: list[str] = []
    warnings: list[str] = []

    ruleset = await repository.latest_rules(tournament_id)
    rules: TournamentRules | None = None

    if ruleset is None:
        errors.append("Tournament rules have not been configured")
    else:
        rules = TournamentRules.model_validate(ruleset.rules)
        errors.extend(scoring_capability_errors(rules))

    registrations = await repository.list_registrations(tournament_id)
    active = [
        item
        for item in registrations
        if item.registration_status in ACTIVE_REGISTRATION_STATUSES
    ]
    approved_main = [
        item
        for item in active
        if item.registration_status == "approved" and not item.is_reserve
    ]

    if len(approved_main) < tournament.minimum_teams:
        errors.append(
            f"Not enough approved teams: {len(approved_main)} of "
            f"{tournament.minimum_teams} required"
        )

    if (
        tournament.maximum_teams is not None
        and len(approved_main) > tournament.maximum_teams
    ):
        errors.append("Approved team count exceeds capacity")

    if any(item.registration_status == "pending" for item in active):
        warnings.append("Some registrations are still pending a decision")

    if rules is not None:
        for membership in approved_main:
            label = membership.display_name or str(membership.team_id)
            roster = await repository.list_roster(membership.id)
            available = [entry for entry in roster if entry.is_available]

            if len(roster) < rules.minimum_roster_size:
                errors.append(
                    f"{label} roster has {len(roster)} players; "
                    f"minimum is {rules.minimum_roster_size}"
                )

            if len(roster) > rules.maximum_roster_size:
                errors.append(
                    f"{label} roster has {len(roster)} players; "
                    f"maximum is {rules.maximum_roster_size}"
                )

            if len(available) < rules.minimum_players_to_start:
                errors.append(
                    f"{label} has fewer than {rules.minimum_players_to_start} "
                    "available players"
                )

            if membership.captain_player_id is None:
                warnings.append(f"{label} has no tournament captain")

            # Rules or player records may have changed since rostering.
            errors.extend(
                f"{label}: {message}"
                for message in await players_eligibility_errors(
                    repository,
                    tournament,
                    rules,
                    [entry.player_id for entry in roster],
                )
            )

        if rules.structure == "groups_knockout":
            if any(item.group_id is None for item in approved_main):
                errors.append("Every approved team must be assigned to a group")

            for group in await repository.list_groups(tournament_id):
                members = await repository.count_group_members(group.id)
                if rules.teams_per_group and members > rules.teams_per_group:
                    errors.append(
                        f"Group {group.name} exceeds "
                        f"{rules.teams_per_group} teams"
                    )

    if not await repository.list_venues(tournament_id):
        warnings.append("No permitted tournament venues configured")

    if tournament.start_date is None:
        warnings.append("Tournament start date is missing")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "registered_teams": len(active),
        "approved_teams": len(approved_main),
        "current_rules_version": ruleset.version if ruleset else None,
    }


async def set_tournament_publication(
    session: AsyncSession,
    tournament_id: UUID,
    publish: bool,
    *,
    actor_id: str | None = None,
) -> Tournament:
    """Publishing announces the competition (e.g. to attract
    registrations), so it requires valid, supported rules rather than
    full scheduling readiness, which is enforced at the SCHEDULED
    transition instead."""

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament publication"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status in {
            TournamentStatus.CANCELLED,
            TournamentStatus.ARCHIVED,
        }:
            raise ConflictError(
                "Tournament cannot be published in this state"
            )

        if tournament.is_published == publish:
            return tournament

        if publish:
            errors = await publication_errors(repository, tournament_id)
            if errors:
                raise ValidationError("; ".join(errors))

        tournament.is_published = publish
        tournament.updated_at = datetime.now(UTC)

        tournament_audit(
            session,
            tournament_id,
            "tournament_published" if publish else "tournament_unpublished",
            {},
            actor_id=actor_id,
        )

        await repository.flush_refresh(tournament)
        return tournament


# Team registration


async def _registration_is_reserve(
    repository: TournamentRepository,
    tournament: Tournament,
    requested_reserve: bool,
) -> bool:
    """Decide main-draw vs reserve placement under the capacity limits.

    Callers hold the tournament row lock, which serializes these counts.
    """

    reserves = await repository.count_registrations(
        tournament.id,
        is_reserve=True,
    )

    if requested_reserve:
        if reserves >= tournament.reserve_team_limit:
            raise ConflictError("Tournament reserve list is full")
        return True

    if tournament.maximum_teams is None:
        return False

    main = await repository.count_registrations(
        tournament.id,
        is_reserve=False,
    )
    if main < tournament.maximum_teams:
        return False

    if reserves < tournament.reserve_team_limit:
        return True

    raise ConflictError("Tournament is full")


async def _admit_team(
    session: AsyncSession,
    repository: TournamentRepository,
    tournament: Tournament,
    payload: TournamentTeamRegister,
    *,
    initial_status: str,
    event_type: str,
    actor_id: str | None,
) -> TournamentTeam:
    team = await session.get(Team, payload.team_id)
    if team is None:
        raise NotFoundError("Team not found")

    if team.status != TeamStatus.ACTIVE or team.archived_at is not None:
        raise ConflictError("Team must be active")

    existing = await repository.get_registration(tournament.id, payload.team_id)

    if existing is not None:
        if existing.registration_status in ACTIVE_REGISTRATION_STATUSES:
            # Idempotent: an active registration is returned as-is.
            return existing

        if (
            existing.registration_status == "rejected"
            and initial_status != "approved"
        ):
            raise ConflictError(
                "This team's registration was rejected; "
                "the organizer must invite it"
            )

    is_reserve = await _registration_is_reserve(
        repository,
        tournament,
        payload.is_reserve,
    )
    display_name = payload.display_name or team.name

    if existing is not None:
        membership = existing
        membership.registration_status = initial_status
        membership.display_name = display_name
        membership.seed = payload.seed
        membership.manager_name = payload.manager_name
        membership.is_reserve = is_reserve
        membership.group_id = None
    else:
        membership = TournamentTeam(
            tournament_id=tournament.id,
            team_id=payload.team_id,
            display_name=display_name,
            seed=payload.seed,
            manager_name=payload.manager_name,
            registration_status=initial_status,
            is_reserve=is_reserve,
        )
        session.add(membership)

    await session.flush()

    tournament_audit(
        session,
        tournament.id,
        event_type,
        {
            "membership_id": str(membership.id),
            "team_id": str(payload.team_id),
            "status": initial_status,
            "is_reserve": is_reserve,
        },
        actor_id=actor_id,
    )

    return await _refreshed(session, membership)


async def register_tournament_team(
    session: AsyncSession,
    tournament_id: UUID,
    payload: TournamentTeamRegister,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament registration"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status != TournamentStatus.REGISTRATION_OPEN:
            raise ConflictError("Tournament registration is not open")

        if tournament.registration_mode != "open":
            raise ConflictError("This tournament requires an invitation")

        now = datetime.now(UTC)

        if (
            tournament.registration_opens_at
            and now < tournament.registration_opens_at
        ):
            raise ConflictError("Registration window has not opened")

        if (
            tournament.registration_closes_at
            and now >= tournament.registration_closes_at
        ):
            raise ConflictError("Registration window has closed")

        return await _admit_team(
            session,
            repository,
            tournament,
            payload,
            initial_status=(
                "pending" if tournament.entry_requires_approval else "approved"
            ),
            event_type="team_registered",
            actor_id=actor_id,
        )


async def invite_tournament_team(
    session: AsyncSession,
    tournament_id: UUID,
    payload: TournamentTeamRegister,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    """Organizer-side entry: works for invitational tournaments and
    outside the public registration window. Invited teams are approved."""

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament invitation"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status not in {
            TournamentStatus.DRAFT,
            TournamentStatus.REGISTRATION_OPEN,
            TournamentStatus.REGISTRATION_CLOSED,
        }:
            raise ConflictError("Teams can no longer be added to this tournament")

        return await _admit_team(
            session,
            repository,
            tournament,
            payload,
            initial_status="approved",
            event_type="team_invited",
            actor_id=actor_id,
        )


async def list_tournament_teams(
    session: AsyncSession,
    tournament_id: UUID,
    registration_status: str | None = None,
) -> list[TournamentTeam]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_registrations(
        tournament_id,
        registration_status=registration_status,
    )


async def list_tournament_teams_page(
    session: AsyncSession,
    tournament_id: UUID,
    *,
    page: int,
    page_size: int,
    registration_status: str | None = None,
    is_reserve: bool | None = None,
    search: str | None = None,
) -> PageResponse[TournamentTeamRead]:
    await get_tournament(session, tournament_id)
    items, total = await TournamentRepository(session).page_registrations(
        tournament_id,
        page=page,
        page_size=page_size,
        registration_status=registration_status,
        is_reserve=is_reserve,
        search=search.strip() if search else None,
    )

    return PageResponse[TournamentTeamRead](
        items=[TournamentTeamRead.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=max(1, -(-total // page_size)),
    )


async def promote_reserve_team(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    replaces_membership_id: UUID | None = None,
    reason: str | None = None,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    """Move a reserve entry into the main draw.

    Allowed until fixtures are scheduled and, when set, until the
    tournament's replacement cutoff. Optionally records the withdrawn
    entry the reserve replaces (each withdrawal can be replaced once).
    """

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament reserve promotion"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        if (
            tournament.replacement_cutoff_at is not None
            and datetime.now(UTC) >= tournament.replacement_cutoff_at
        ):
            raise ConflictError("The tournament replacement cutoff has passed")

        membership = await require_membership(repository, tournament_id, membership_id)

        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            raise ConflictError("Only active reserve entries can be promoted")

        if not membership.is_reserve:
            raise ConflictError("This team is already in the main draw")

        if replaces_membership_id is not None:
            if replaces_membership_id == membership_id:
                raise ValidationError("A team cannot replace itself")

            replaced = await require_membership(
                repository,
                tournament_id,
                replaces_membership_id,
            )
            if replaced.registration_status != "withdrawn":
                raise ConflictError("Only a withdrawn team can be replaced")

            if await repository.get_replacement_for(replaces_membership_id) is not None:
                raise ConflictError("This withdrawn team has already been replaced")

        if tournament.maximum_teams is not None:
            main = await repository.count_registrations(tournament_id, is_reserve=False)
            if main >= tournament.maximum_teams:
                raise ConflictError("The main draw is full")

        membership.is_reserve = False
        membership.replaces_membership_id = replaces_membership_id

        tournament_audit(
            session,
            tournament_id,
            "reserve_promoted",
            {
                "membership_id": str(membership_id),
                "replaces_membership_id": (
                    str(replaces_membership_id) if replaces_membership_id else None
                ),
                "reason": reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, membership)


async def decide_tournament_registration(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    approve: bool,
    reason: str | None = None,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament registration"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status not in {
            TournamentStatus.REGISTRATION_OPEN,
            TournamentStatus.REGISTRATION_CLOSED,
        }:
            raise ConflictError("Registration decisions are locked")

        membership = await repository.get_membership(tournament_id, membership_id)
        if membership is None:
            raise NotFoundError("Registration not found")

        target = "approved" if approve else "rejected"

        if membership.registration_status == target:
            return membership

        if membership.registration_status != "pending":
            raise ConflictError(
                "Only pending registrations can be approved or rejected"
            )

        if not approve and not (reason and reason.strip()):
            raise ValidationError("Rejection reason is required")

        membership.registration_status = target
        if not approve:
            membership.group_id = None

        tournament_audit(
            session,
            tournament_id,
            "registration_decided",
            {
                "membership_id": str(membership_id),
                "decision": target,
                "reason": reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, membership)


async def withdraw_tournament_team(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    reason: str,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament withdrawal"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status in CONFIGURATION_LOCKED_STATUSES:
            raise ConflictError(
                "Teams cannot withdraw after fixtures are scheduled"
            )

        membership = await require_membership(
            repository,
            tournament_id,
            membership_id,
        )

        if membership.registration_status == "withdrawn":
            return membership

        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            raise ConflictError("Only active registrations can be withdrawn")

        if await repository.team_has_matches(tournament_id, membership.team_id):
            raise ConflictError(
                "Team already has tournament fixtures; remove them first"
            )

        previous = membership.registration_status
        membership.registration_status = "withdrawn"
        membership.group_id = None

        tournament_audit(
            session,
            tournament_id,
            "team_withdrawn",
            {
                "membership_id": str(membership_id),
                "previous_status": previous,
                "reason": reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, membership)


async def assign_tournament_group(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    group_id: UUID | None,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament group assignment"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        membership = await require_membership(
            repository,
            tournament_id,
            membership_id,
        )

        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            raise ConflictError("Inactive registrations cannot join a group")

        if membership.group_id == group_id:
            return membership

        if group_id is not None:
            group = await repository.get_group(tournament_id, group_id)
            if group is None:
                raise NotFoundError("Tournament group not found")

            ruleset = await repository.latest_rules(tournament_id)
            if ruleset is not None:
                rules = TournamentRules.model_validate(ruleset.rules)
                if (
                    rules.teams_per_group is not None
                    and await repository.count_group_members(group_id)
                    >= rules.teams_per_group
                ):
                    raise ConflictError(
                        f"Group {group.name} already has "
                        f"{rules.teams_per_group} teams"
                    )

        membership.group_id = group_id

        tournament_audit(
            session,
            tournament_id,
            "group_assigned",
            {
                "membership_id": str(membership_id),
                "group_id": str(group_id) if group_id else None,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, membership)


async def set_tournament_captain(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    player_id: UUID,
    *,
    actor_id: str | None = None,
) -> TournamentTeam:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament captain"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_not_final(tournament)

        membership = await require_membership(
            repository,
            tournament_id,
            membership_id,
        )

        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            raise ConflictError("Inactive registrations cannot name a captain")

        entry = await repository.get_roster_player(membership_id, player_id)
        if entry is None:
            raise ValidationError(
                "Captain must be on the team's tournament roster"
            )

        if not entry.is_available:
            raise ValidationError("Captain must be available")

        if membership.captain_player_id == player_id:
            return membership

        membership.captain_player_id = player_id

        tournament_audit(
            session,
            tournament_id,
            "captain_set",
            {
                "membership_id": str(membership_id),
                "player_id": str(player_id),
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, membership)


# Tournament rosters


async def list_tournament_roster(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
) -> list[TournamentRoster]:
    repository = TournamentRepository(session)
    await require_membership(repository, tournament_id, membership_id)
    return await repository.list_roster(membership_id)


async def list_roster_candidates(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
) -> list[RosterCandidateRead]:
    """Active squad players not yet on this roster, each marked with the
    reasons (if any) the roster add would be refused."""

    repository = TournamentRepository(session)
    tournament = await get_tournament(session, tournament_id)
    membership = await require_membership(repository, tournament_id, membership_id)

    ruleset = await repository.latest_rules(tournament_id)
    rules = TournamentRules.model_validate(ruleset.rules) if ruleset else None

    on_roster = {entry.player_id for entry in await repository.list_roster(membership_id)}
    elsewhere = await repository.players_on_other_rosters(
        tournament_id,
        exclude_membership_id=membership_id,
    )
    squad = await MatchSetupRepository(session).get_active_squad(membership.team_id)

    candidates = []
    for item in squad:
        if item.player_id in on_roster:
            continue

        reasons = []
        if item.player_id in elsewhere:
            reasons.append("Already on another team's roster in this tournament")

        if rules is not None:
            reasons.extend(player_errors(item.player, tournament, rules, label="Player"))

        candidates.append(
            RosterCandidateRead(
                player_id=item.player_id,
                full_name=item.player.full_name,
                role=item.role.value,
                squad_number=item.squad_number,
                eligible=not reasons,
                reasons=reasons,
            )
        )

    return candidates


async def add_tournament_roster_player(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    payload: RosterAdd,
    *,
    actor_id: str | None = None,
) -> TournamentRoster:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament roster"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_roster_editable(tournament)

        membership = await require_membership(
            repository,
            tournament_id,
            membership_id,
        )

        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            raise ConflictError("Inactive registration cannot edit roster")

        player = await session.get(Player, payload.player_id)
        if player is None:
            raise NotFoundError("Player not found")

        if player.status != PlayerStatus.ACTIVE:
            raise ConflictError("Player must be active")

        existing = await repository.get_roster_player(
            membership_id,
            payload.player_id,
        )
        if existing is not None:
            return existing

        squad = await MatchSetupRepository(session).get_active_squad_memberships(
            membership.team_id,
            {payload.player_id},
        )
        if payload.player_id not in squad:
            raise ValidationError(
                "Player must belong to the team's active squad"
            )

        if await repository.player_registered_elsewhere(
            tournament_id,
            payload.player_id,
            exclude_membership_id=membership_id,
        ):
            raise ConflictError(
                "Player is already on another team's roster "
                "in this tournament"
            )

        ruleset = await repository.latest_rules(tournament_id)
        if ruleset is None:
            raise ConflictError("Create tournament rules first")

        rules = TournamentRules.model_validate(ruleset.rules)
        roster = await repository.list_roster(membership_id)

        if len(roster) >= rules.maximum_roster_size:
            raise ConflictError("Maximum tournament squad size reached")

        ineligible = player_errors(player, tournament, rules)
        if ineligible:
            raise ValidationError("; ".join(ineligible))

        item = TournamentRoster(
            tournament_team_id=membership_id,
            player_id=payload.player_id,
            role=payload.role,
        )
        session.add(item)

        tournament_audit(
            session,
            tournament_id,
            "roster_player_added",
            {
                "membership_id": str(membership_id),
                "player_id": str(payload.player_id),
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, item)


async def remove_tournament_roster_player(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    player_id: UUID,
    *,
    actor_id: str | None = None,
) -> dict[str, bool]:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament roster"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_roster_editable(tournament)

        membership = await require_membership(
            repository,
            tournament_id,
            membership_id,
        )

        entry = await repository.get_roster_player(membership_id, player_id)
        if entry is None:
            raise NotFoundError("Player is not on this tournament roster")

        if entry.locked_at is not None:
            raise ConflictError("Roster entry is locked")

        if membership.captain_player_id == player_id:
            membership.captain_player_id = None

        await session.delete(entry)

        tournament_audit(
            session,
            tournament_id,
            "roster_player_removed",
            {
                "membership_id": str(membership_id),
                "player_id": str(player_id),
            },
            actor_id=actor_id,
        )

        await session.flush()
        return {"removed": True}


async def set_roster_availability(
    session: AsyncSession,
    tournament_id: UUID,
    membership_id: UUID,
    player_id: UUID,
    is_available: bool,
    reason: str | None = None,
    *,
    actor_id: str | None = None,
) -> TournamentRoster:
    """Availability (injury, absence) can change even after rosters lock."""

    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament roster"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_not_final(tournament)

        await require_membership(repository, tournament_id, membership_id)

        entry = await repository.get_roster_player(membership_id, player_id)
        if entry is None:
            raise NotFoundError("Player is not on this tournament roster")

        if entry.is_available == is_available:
            return entry

        entry.is_available = is_available

        tournament_audit(
            session,
            tournament_id,
            "roster_availability_changed",
            {
                "membership_id": str(membership_id),
                "player_id": str(player_id),
                "is_available": is_available,
                "reason": reason,
            },
            actor_id=actor_id,
        )

        return await _refreshed(session, entry)


async def _lock_rosters(
    repository: TournamentRepository,
    tournament: Tournament,
    now: datetime,
) -> int:
    locked = 0

    for membership in await repository.list_registrations(tournament.id):
        if membership.registration_status not in ACTIVE_REGISTRATION_STATUSES:
            continue

        for entry in await repository.list_roster(membership.id):
            if entry.locked_at is None:
                entry.locked_at = now
                locked += 1

    if tournament.roster_lock_at is None or tournament.roster_lock_at > now:
        tournament.roster_lock_at = now

    return locked


async def lock_tournament_rosters(
    session: AsyncSession,
    tournament_id: UUID,
    reason: str | None = None,
    *,
    actor_id: str | None = None,
) -> dict[str, int]:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament roster lock"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_not_final(tournament)

        now = datetime.now(UTC)
        locked = await _lock_rosters(repository, tournament, now)
        tournament.updated_at = now

        tournament_audit(
            session,
            tournament_id,
            "rosters_locked",
            {"locked_entries": locked, "reason": reason},
            actor_id=actor_id,
        )

        await session.flush()
        return {"locked_entries": locked}


# Groups


async def list_tournament_groups(
    session: AsyncSession,
    tournament_id: UUID,
) -> list[TournamentGroup]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_groups(tournament_id)


async def create_tournament_group(
    session: AsyncSession,
    tournament_id: UUID,
    name: str,
    sort_order: int = 0,
    *,
    actor_id: str | None = None,
) -> TournamentGroup:
    repository = TournamentRepository(session)
    clean_name = name.strip()

    if not clean_name:
        raise ValidationError("Group name is required")

    async with tournament_transaction(session, "Tournament group"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        existing = await repository.get_group_by_name(tournament_id, clean_name)
        if existing is not None:
            return existing

        group = TournamentGroup(
            tournament_id=tournament_id,
            name=clean_name,
            sort_order=sort_order,
        )
        session.add(group)
        await session.flush()

        tournament_audit(
            session,
            tournament_id,
            "group_created",
            {"group_id": str(group.id), "name": clean_name},
            actor_id=actor_id,
        )

        return await _refreshed(session, group)


async def delete_tournament_group(
    session: AsyncSession,
    tournament_id: UUID,
    group_id: UUID,
    *,
    actor_id: str | None = None,
) -> dict[str, bool]:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament group"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        group = await repository.get_group(tournament_id, group_id)
        if group is None:
            raise NotFoundError("Tournament group not found")

        if await repository.count_group_members(group_id):
            raise ConflictError("Move teams out of the group before deleting it")

        await session.delete(group)

        tournament_audit(
            session,
            tournament_id,
            "group_deleted",
            {"group_id": str(group_id)},
            actor_id=actor_id,
        )

        await session.flush()
        return {"removed": True}


# Venues


async def list_tournament_venues(
    session: AsyncSession,
    tournament_id: UUID,
) -> list[TournamentVenue]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_venues(tournament_id)


async def assign_tournament_venue(
    session: AsyncSession,
    tournament_id: UUID,
    venue_id: UUID,
    *,
    actor_id: str | None = None,
) -> TournamentVenue:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament venue"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)
        await require_active_venue(session, venue_id)

        existing = await repository.get_venue_link(tournament_id, venue_id)
        if existing is not None:
            return existing

        item = TournamentVenue(tournament_id=tournament_id, venue_id=venue_id)
        session.add(item)

        tournament_audit(
            session,
            tournament_id,
            "venue_assigned",
            {"venue_id": str(venue_id)},
            actor_id=actor_id,
        )

        return await _refreshed(session, item)


async def remove_tournament_venue(
    session: AsyncSession,
    tournament_id: UUID,
    venue_id: UUID,
    *,
    actor_id: str | None = None,
) -> dict[str, bool]:
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament venue"):
        tournament = await locked_tournament(repository, tournament_id)
        ensure_configuration_editable(tournament)

        if tournament.primary_venue_id == venue_id:
            raise ConflictError("Cannot remove the primary venue")

        if await repository.tournament_match_uses_venue(tournament_id, venue_id):
            raise ConflictError("Venue is assigned to a tournament match")

        item = await repository.get_venue_link(tournament_id, venue_id)
        if item is None:
            raise NotFoundError("Tournament venue not found")

        await session.delete(item)

        tournament_audit(
            session,
            tournament_id,
            "venue_removed",
            {"venue_id": str(venue_id)},
            actor_id=actor_id,
        )

        await session.flush()
        return {"removed": True}


# Audit trail


async def list_tournament_audit(
    session: AsyncSession,
    tournament_id: UUID,
    limit: int = 100,
) -> list[TournamentAuditEvent]:
    await get_tournament(session, tournament_id)
    return await TournamentRepository(session).list_audit_events(
        tournament_id,
        limit=limit,
    )


async def get_tournament_transitions(
    session: AsyncSession,
    tournament_id: UUID,
) -> dict[str, Any]:
    tournament = await get_tournament(session, tournament_id)
    allowed = sorted(
        TOURNAMENT_TRANSITIONS.get(tournament.status, set()),
        key=lambda item: list(TournamentStatus).index(item),
    )

    return {
        "current": tournament.status,
        "allowed": allowed,
        "reason_required": [
            item for item in allowed if item in REASON_REQUIRED_TARGETS
        ],
    }
