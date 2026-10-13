from __future__ import annotations
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    bowler_quota_policy: Literal["engine_default"] = "engine_default"
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
    powerplay_segments: list[dict] = Field(default_factory=list)
    mandatory_break_minutes: int = Field(default=0, ge=0)
    innings_time_minutes: int | None = Field(default=None, ge=1)
    timeout_minutes: int = Field(default=0, ge=0)
    allowed_outcomes: list[str] = Field(
    default_factory=lambda: ["win", "tie"])
    allow_match_overrides: bool = False


    @model_validator(mode="after")
    def validate_consistency(self):
        if self.minimum_players_to_start > self.players_per_side:
            raise ValueError("Minimum starting players cannot exceed players per side")

        if self.maximum_roster_size < self.minimum_roster_size:
            raise ValueError("Maximum roster must be >= minimum roster")

        if self.minimum_roster_size < self.players_per_side:
            raise ValueError("Minimum roster must accommodate players per side")

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

        return self


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
    "hundred": {
        "overs_per_innings": 20,
        "players_per_side": 11,
    },
    "indoor": {
        "overs_per_innings": 16,
        "players_per_side": 8,
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
    preset = FORMAT_PRESETS[format_code]
    players = preset["players_per_side"]

    return TournamentRules(
        format_code=format_code,
        overs_per_innings=preset["overs_per_innings"],
        players_per_side=players,
        minimum_players_to_start=players,
        minimum_roster_size=players,
        maximum_roster_size=max(players, 18),
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

    if rules.format_code == "hundred":
        errors.append(
            "Authentic Hundred-style sets and "
            "bowler allocation are not implemented"
        )

    if rules.format_code == "indoor":
        errors.append("Special indoor-cricket scoring rules are not implemented")

    if rules.balls_per_over != 6:
        errors.append(
            "Non-six-ball overs require additional "
            "end-to-end scoring compatibility tests"
        )

    if rules.innings_per_team != 1:
        errors.append(
            "Multi-innings competition mode has not "
            "been certified for tournament activation"
        )

    if rules.minimum_players_to_start != rules.players_per_side:
        errors.append("Stage 10 match readiness requires a complete playing side")

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

    if rules.overseas_player_limit is not None:
        errors.append("Overseas-player nationality enforcement is not implemented")

    if rules.best_of_finals > 1:
        errors.append("Best-of-N scheduling is not implemented")

    if rules.points.bonus_points_enabled:
        errors.append("Bonus point calculation is not implemented")

    return errors


def validate_for_activation(rules: TournamentRules) -> None:
    errors = scoring_capability_errors(rules)

    if errors:
        raise ValidationError("Tournament rules cannot be activated: " + "; ".join(errors))

def match_config_from_rules(rules: TournamentRules) -> dict[str, int]:
    """Match columns that a tournament rule version dictates."""

    return {
        "players_per_side": rules.players_per_side,
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
