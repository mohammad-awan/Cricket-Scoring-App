from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID


RUN_OUTCOMES = {0, 1, 2, 3, 4, 6}


@dataclass(frozen=True)
class DerivedState:
    total_runs: int
    legal_balls: int
    wickets: int
    striker_id: UUID
    non_striker_id: UUID


@dataclass(frozen=True)
class DeliveryComponents:
    batter_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    extra_runs: int
    total_runs: int
    running_runs: int
    is_legal_ball: bool


@dataclass(
    frozen=True
)
class ChaseState:

    target: int

    batting_runs: int

    bowling_runs: int
