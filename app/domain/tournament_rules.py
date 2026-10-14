from __future__ import annotations
import hashlib
import json
from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.exceptions import ValidationError

FormatCode = Literal[
    "t20",
    "odi",
    "t10",
    "hundred",
    "indoor",
    "gully",
    "custom"
]
StructureCode = Literal[
    "single_round_robin",
    "double_round_robin",
    "knockout",
    "groups_knockout",
    "hybrid",
]
TieBreaker = Literal[
    "points",
    "wins",
    "net_run_rate",
    "head_to_head",
    "wickets",
    "drawing_of_lots",
]
ExtraKind = Literal["wide", "no_ball", "bye", "leg_bye"]
MatchOutcome = Literal[
    "win",
    "tie",
    "no_result",
    "draw",
    "forfeit",
    "abandoned",
    "postponed",
]
BowlerQuotaPolicy = Literal["engine_default", "fixed", "unlimited"]
EligibleSex = Literal["open", "male", "female"]

ALL_EXTRAS: tuple[str, ...] = ("wide", "no_ball", "bye", "leg_bye")


class PowerplaySegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_over: int = Field(ge=1)
    to_over: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self):
        if self.to_over < self.from_over:
            raise ValueError("Powerplay to_over must not be before from_over")
        return self


class EligibilityPolicy(BaseModel):
    """Player eligibility for tournament rosters and playing XIs."""

    model_config = ConfigDict(extra="forbid")

    minimum_age: int | None = Field(default=None, ge=5, le=100)
    maximum_age: int | None = Field(default=None, ge=5, le=100)
    # Ages are measured on this date; defaults to the tournament start
    # date, then to the day the player is added.
    age_reference_date: date | None = None
    sex: EligibleSex = "open"
    # Players whose nationality differs count against overseas_player_limit.
    home_nationality: str | None = Field(default=None, max_length=80)

    @field_validator("home_nationality", mode="before")
    @classmethod
    def strip_nationality(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_ages(self):
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.maximum_age < self.minimum_age
        ):
            raise ValueError("Maximum age must be >= minimum age")
        return self

    @property
    def has_age_limit(self) -> bool:
        return self.minimum_age is not None or self.maximum_age is not None


class StandingsPolicy(BaseModel):
    """How special results feed each ranking metric.

    Stage 11 stores and versions these definitions; Stage 13 applies
    them when computing standings from finalized results.
    """

    model_config = ConfigDict(extra="forbid")

    # Abandoned without a result: share no-result points, or award none.
    abandoned_match_points: Literal["no_result", "none"] = "no_result"
    # Abandoned matches never contribute runs or overs to net run rate.
    abandoned_in_net_run_rate: Literal["excluded"] = "excluded"
    # Forfeits/walkovers count as a win for the "wins" metric.
    forfeit_counts_as_win: bool = True
    # Forfeits are left out of NRR, or the winner is credited with its
    # full overs quota and zero runs against.
    forfeit_net_run_rate: Literal["excluded", "winner_credited_full_overs"] = "excluded"
    # A side bowled out is charged its full overs quota (ICC convention),
    # or only the overs it actually faced.
    all_out_net_run_rate_overs: Literal["full_quota", "overs_faced"] = "full_quota"
    # Partial overs count as balls / balls_per_over (4.3 overs = 4.5).
    partial_overs: Literal["ball_fraction"] = "ball_fraction"
    # DLS results use the revised target and overs, or the actual scores.
    dls_net_run_rate_basis: Literal["revised_target", "actual_scores"] = "revised_target"
    # Head-to-head looks only at completed matches between the tied sides.
    head_to_head_scope: Literal["completed_matches", "all_results"] = "completed_matches"
    # The "wickets" tie-breaker ranks most wickets taken, or fewest lost.
    wickets_metric: Literal["most_wickets_taken", "fewest_wickets_lost"] = "most_wickets_taken"
    # Disciplinary deductions reduce points only, never other metrics.
    point_deductions_affect: Literal["points_only"] = "points_only"


class PointsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    win: int = Field(default=2, ge=0)
    tie: int = Field(default=1, ge=0)
    no_result: int = Field(default=1, ge=0)
    draw: int = Field(default=1, ge=0)
    loss: int = Field(default=0, ge=0)
    forfeit: int = Field(default=0, ge=0)
    bonus_points_enabled: bool = False



class TournamentRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_code: FormatCode = "t20"
    structure: StructureCode = "single_round_robin"
    overs_per_innings: int = Field(default=20, ge=1)
    balls_per_over: int = Field(default=6, ge=1)
    innings_per_team: int = Field(default=1, ge=1)
    players_per_side: int = Field(default=11, ge=2)
    minimum_players_to_start: int = Field(default=11, ge=2)
    # engine_default: one fifth of the innings overs, rounded up.
    bowler_quota_policy: BowlerQuotaPolicy = "engine_default"
    overs_per_bowler: int | None = Field(default=None, ge=1)
    permitted_extras: list[ExtraKind] = Field(
        default_factory=lambda: list(ALL_EXTRAS)
    )
    minimum_roster_size: int = Field(default=11, ge=2)
    maximum_roster_size: int = Field(default=18, ge=2)
    overseas_player_limit: int | None = Field(default=None, ge=0)
    teams_per_group: int | None = Field(default=None, ge=2)
    best_of_finals: int = Field(default=1, ge=1)
    points: PointsPolicy = Field(default_factory=PointsPolicy)
    tie_breakers: list[TieBreaker] = Field(
         default_factory=lambda: [
            "points",
            "wins",
            "net_run_rate",
            "head_to_head",
            "drawing_of_lots",
        ]
    )
    super_over_enabled: bool = False
    dls_enabled: bool = False
    impact_player_enabled: bool = False
    reduced_overs_enabled: bool = False
    powerplay_segments: list[PowerplaySegment] = Field(default_factory=list)
    mandatory_break_minutes: int = Field(default=0, ge=0)
    innings_time_minutes: int | None = Field(default=None, ge=1)
    timeout_minutes: int = Field(default=0, ge=0)
    allowed_outcomes: list[MatchOutcome] = Field(
        default_factory=lambda: ["win", "tie"]
    )
    allow_match_overrides: bool = False
    eligibility: EligibilityPolicy = Field(default_factory=EligibilityPolicy)
    standings_policy: StandingsPolicy = Field(default_factory=StandingsPolicy)


    @model_validator(mode="after")
    def validate_consistency(self):
        if self.minimum_players_to_start > self.players_per_side:
            raise ValueError("Minimum starting players cannot exceed players per side")

        if self.maximum_roster_size < self.minimum_roster_size:
            raise ValueError("Maximum roster must be >= minimum roster")

        if self.minimum_roster_size < self.minimum_players_to_start:
            raise ValueError(
                "Minimum roster must accommodate the minimum players to start"
            )

        if len(self.tie_breakers) != len(set(self.tie_breakers)):
            raise ValueError("Tie breakers cannot contain duplicates")

        if (
            "drawing_of_lots" in self.tie_breakers
            and self.tie_breakers[-1] != "drawing_of_lots"
        ):
            raise ValueError("Drawing of lots must be the final tie breaker")

        if self.best_of_finals % 2 == 0:
            raise ValueError("Best-of-N finals must use an odd N")

        if self.structure == "groups_knockout" and self.teams_per_group is None:
            raise ValueError(
                "Groups and knockout format requires "
                "teams_per_group"
            )

        self._validate_bowler_quota()

        if len(self.permitted_extras) != len(set(self.permitted_extras)):
            raise ValueError("Permitted extras cannot contain duplicates")

        if len(self.allowed_outcomes) != len(set(self.allowed_outcomes)):
            raise ValueError("Allowed outcomes cannot contain duplicates")

        if "win" not in self.allowed_outcomes:
            raise ValueError("Allowed outcomes must include win")

        self._validate_powerplays()

        if self.overseas_player_limit is not None:
            if self.eligibility.home_nationality is None:
                raise ValueError(
                    "An overseas player limit requires "
                    "eligibility.home_nationality"
                )
            if self.overseas_player_limit > self.players_per_side:
                raise ValueError(
                    "Overseas player limit cannot exceed players per side"
                )

        return self

    def _validate_bowler_quota(self) -> None:
        if self.bowler_quota_policy != "fixed":
            if self.overs_per_bowler is not None:
                raise ValueError(
                    "overs_per_bowler is only used with the fixed quota policy"
                )
            return

        if self.overs_per_bowler is None:
            raise ValueError("The fixed quota policy requires overs_per_bowler")

        if self.overs_per_bowler > self.overs_per_innings:
            raise ValueError("Overs per bowler cannot exceed overs per innings")

        # Worst case: a side that starts short must still finish its overs.
        if self.overs_per_bowler * self.minimum_players_to_start < self.overs_per_innings:
            raise ValueError(
                "Bowler quota is too small for the side "
                "to bowl its full overs"
            )

    def _validate_powerplays(self) -> None:
        previous_end = 0

        for segment in sorted(self.powerplay_segments, key=lambda item: item.from_over):
            if segment.to_over > self.overs_per_innings:
                raise ValueError("Powerplay segments must fit inside the innings")

            if segment.from_over <= previous_end:
                raise ValueError("Powerplay segments cannot overlap")

            previous_end = segment.to_over


FORMAT_PRESETS = {
    "t20": {
        "overs_per_innings": 20,
        "players_per_side": 11,
    },
    "odi": {
        "overs_per_innings": 50,
        "players_per_side": 11,
    },
    "t10": {
        "overs_per_innings": 10,
        "players_per_side": 11,
    },
    # 100 balls as 20 five-ball overs; each bowler at most 20 balls.
    "hundred": {
        "overs_per_innings": 20,
        "players_per_side": 11,
        "balls_per_over": 5,
        "bowler_quota_policy": "fixed",
        "overs_per_bowler": 4,
    },
    # Eight-a-side, 16 overs, every player bowls two overs.
    "indoor": {
        "overs_per_innings": 16,
        "players_per_side": 8,
        "bowler_quota_policy": "fixed",
        "overs_per_bowler": 2,
    },
    "gully": {
        "overs_per_innings": 5,
        "players_per_side": 6,
    },
    "custom": {
        "overs_per_innings": 10,
        "players_per_side": 11,
    },
}


def rules_preset(format_code: FormatCode) -> TournamentRules:
    """Starting values only: every field stays editable afterwards."""

    preset = dict(FORMAT_PRESETS[format_code])
    players = preset["players_per_side"]

    return TournamentRules(
        format_code=format_code,
        minimum_players_to_start=players,
        minimum_roster_size=players,
        maximum_roster_size=max(players, 18),
        **preset,
    )


def checksum_rules(rules: TournamentRules) -> str:
    canonical = json.dumps(
        rules.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scoring_capability_errors(rules: TournamentRules) -> list[str]:
    errors = []

    # Format presets, over length, innings count and side sizes are all
    # handled by the scoring engine. Only features that need workflows the
    # engine does not have yet are blocked below.

    if rules.super_over_enabled:
        errors.append("Super over workflow is not implemented")

    if rules.dls_enabled:
        errors.append("DLS calculation is not implemented")

    if rules.impact_player_enabled:
        errors.append("Impact-player substitution is not implemented")

    if rules.reduced_overs_enabled:
        errors.append("Reduced-overs match adjustment is not fully implemented")

    if rules.powerplay_segments:
        errors.append("Powerplay enforcement is not implemented")

    if rules.allow_match_overrides:
        errors.append("Approved per-match rules override workflow is not implemented")

    unsupported_outcomes = set(rules.allowed_outcomes) - {"win", "tie"}

    if unsupported_outcomes:
        errors.append(
            "The requested automatic outcome workflows "
            "require additional lifecycle support: "
            + ", ".join(sorted(unsupported_outcomes))
        )

    if rules.best_of_finals > 1:
        errors.append("Best-of-N scheduling is not implemented")

    if rules.points.bonus_points_enabled:
        errors.append("Bonus point calculation is not implemented")

    return errors


def validate_for_activation(rules: TournamentRules) -> None:
    errors = scoring_capability_errors(rules)

    if errors:
        raise ValidationError("Tournament rules cannot be activated: " + "; ".join(errors))

def bowler_quota_overs(effective_rules: dict[str, Any] | None, total_overs: int) -> int | None:
    """Overs one bowler may bowl under a match's locked rule snapshot.

    Returns None for no limit. Matches without a snapshot (friendlies,
    legacy tournaments, unlocked drafts) keep the engine default.
    """

    engine_default = -(-total_overs // 5)

    if not effective_rules:
        return engine_default

    policy = effective_rules.get("bowler_quota_policy", "engine_default")

    if policy == "unlimited":
        return None

    if policy == "fixed" and effective_rules.get("overs_per_bowler"):
        return int(effective_rules["overs_per_bowler"])

    return engine_default


def disallowed_extras(
    effective_rules: dict[str, Any] | None,
    *,
    wide: bool,
    no_ball: bool,
    bye: bool,
    leg_bye: bool,
) -> list[str]:
    """Extras on a delivery that the match's rule snapshot does not permit."""

    if not effective_rules:
        return []

    permitted = set(effective_rules.get("permitted_extras", ALL_EXTRAS))
    used = {
        "wide": wide,
        "no_ball": no_ball,
        "bye": bye,
        "leg_bye": leg_bye,
    }

    return [kind for kind, present in used.items() if present and kind not in permitted]


def match_config_from_rules(rules: TournamentRules) -> dict[str, int]:
    """Match columns that a tournament rule version dictates."""

    return {
        "players_per_side": rules.players_per_side,
        "minimum_players_to_start": rules.minimum_players_to_start,
        "total_overs": rules.overs_per_innings,
        "balls_per_over": rules.balls_per_over,
        "innings_per_team": rules.innings_per_team,
    }


def match_config_mismatches(
    rules: TournamentRules,
    config: dict[str, object],
) -> list[str]:
    return [
        f"{field} must be {expected} for this tournament"
        for field, expected in match_config_from_rules(rules).items()
        if config.get(field) != expected
    ]
