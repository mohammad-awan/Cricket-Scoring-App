
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Literal, Sequence


class FixtureError(ValueError):
    """Raised when fixture planning input is invalid."""


@dataclass(frozen=True)
class Pairing:
    round_number: int
    home_team_id: str | None
    away_team_id: str | None
    leg: int = 1

    @property
    def is_bye(self) -> bool:
        return self.home_team_id is None or self.away_team_id is None


@dataclass(frozen=True)
class KnockoutSlot:
    round_number: int
    match_number: int
    home_team_id: str | None
    away_team_id: str | None
    home_source: str | None = None
    away_source: str | None = None


def validate_teams(team_ids: Sequence[str]) -> list[str]:
    """
    Validate tournament team IDs.

    Requirements:
    - At least two teams
    - Non-empty string IDs
    - No duplicate IDs
    """
    teams = list(team_ids)

    if len(teams) < 2:
        raise FixtureError("At least two teams are required.")

    if any(
        not isinstance(team, str) or not team.strip()
        for team in teams
    ):
        raise FixtureError(
            "Team IDs must be non-empty strings."
        )

    if len(teams) != len(set(teams)):
        raise FixtureError(
            "Duplicate team IDs are not allowed."
        )

    return teams


def round_robin(
    team_ids: Sequence[str],
    *,
    legs: Literal[1, 2] = 1,
    shuffle: bool = False,
    seed: int | None = None,
) -> list[Pairing]:
    """
    Generate round-robin fixtures using the circle method.

    Supports:
    - Single round-robin
    - Double round-robin
    - Odd team counts with BYEs
    - Deterministic seeded random draws

    The second leg reverses home and away.
    """
    teams = validate_teams(team_ids)

    if legs not in (1, 2):
        raise FixtureError(
            "Legs must be 1 or 2."
        )

    if shuffle:
        if seed is None:
            raise FixtureError(
                "A seed is required for reproducible draws."
            )

        random.Random(seed).shuffle(teams)

    if len(teams) % 2 != 0:
        teams.append(None)

    size = len(teams)
    rounds_per_leg = size - 1
    half = size // 2

    rotation = teams[:]
    first_leg: list[Pairing] = []

    for round_index in range(rounds_per_leg):
        round_number = round_index + 1

        for index in range(half):
            first = rotation[index]
            second = rotation[size - 1 - index]

            # Alternate home/away orientation.
            if (round_index + index) % 2:
                first, second = second, first

            first_leg.append(
                Pairing(
                    round_number=round_number,
                    home_team_id=first,
                    away_team_id=second,
                    leg=1,
                )
            )

        # Circle-method rotation:
        # Keep the first position fixed.
        rotation = (
            [rotation[0], rotation[-1]]
            + rotation[1:-1]
        )

    if legs == 1:
        return first_leg

    second_leg = [
        Pairing(
            round_number=(
                item.round_number + rounds_per_leg
            ),
            home_team_id=item.away_team_id,
            away_team_id=item.home_team_id,
            leg=2,
        )
        for item in first_leg
    ]

    return first_leg + second_leg


def random_round_robin(
    team_ids: Sequence[str],
    *,
    seed: int,
    legs: Literal[1, 2] = 1,
) -> list[Pairing]:
    """
    Generate reproducible randomized round-robin fixtures.

    The same teams, order, seed and legs produce
    the same fixture list.
    """
    return round_robin(
        team_ids,
        legs=legs,
        shuffle=True,
        seed=seed,
    )


def validate_manual(
    pairings: Sequence[Pairing],
    *,
    allowed_team_ids: Sequence[str],
    legs: Literal[1, 2] = 1,
) -> None:
    """
    Validate a complete manual round-robin draw.

    Checks:
    - Valid team IDs
    - No self-opponents
    - No duplicate opponent pairs within a leg
    - No team appears twice in the same round
    - All required pairings are present

    Dates, times and venues must be checked separately.
    """
    teams = set(
        validate_teams(allowed_team_ids)
    )

    if legs not in (1, 2):
        raise FixtureError("Legs must be 1 or 2.")

    sorted_teams = sorted(teams)

    expected_pairs = {
        frozenset((a, b))
        for index, a in enumerate(sorted_teams)
        for b in sorted_teams[index + 1:]
    }

    seen: dict[frozenset[str], set[int]] = {}
    round_teams: dict[int, set[str]] = {}

    for fixture in pairings:
        if fixture.is_bye:
            raise FixtureError("Manual fixtures must contain two teams.")

        a = fixture.home_team_id
        b = fixture.away_team_id

        if a not in teams or b not in teams:
            raise FixtureError("Unknown team in fixture.")

        if a == b:
            raise FixtureError("A team cannot play itself.")

        if fixture.round_number < 1:
            raise FixtureError("Round number must be positive.")

        if fixture.leg < 1 or fixture.leg > legs:
            raise FixtureError("Invalid leg number.")

        playing = round_teams.setdefault(fixture.round_number, set())

        if a in playing or b in playing:
            raise FixtureError("A team appears twice in one round.")

        playing.update((a, b))

        key = frozenset((a, b))
        used_legs = seen.setdefault(key, set())

        if fixture.leg in used_legs:
            raise FixtureError("Duplicate opponent pairing in a leg.")

        used_legs.add(fixture.leg)

    if set(seen) != expected_pairs:
        raise FixtureError("Manual draw has missing or unexpected pairings.")

    expected_legs = set(range(1, legs + 1))

    if any(used_legs != expected_legs for used_legs in seen.values()):
        raise FixtureError("Every opponent pair must occur once per leg.")


def knockout_bracket(team_ids: Sequence[str], *, seed: int | None = None) -> list[KnockoutSlot]:
    """
    Plan a single-elimination knockout bracket.

    Supports:
    - Two or more teams
    - Seeded random ordering
    - Preliminary-round BYEs
    - Winner dependency placeholders

    Bracket placeholders are not actual Match records.
    Official results must resolve dependencies before
    downstream matches become active.
    """
    teams = validate_teams(team_ids)

    if seed is not None:
        random.Random(seed).shuffle(teams)

    count = len(teams)
    bracket_size = 1 << (count - 1).bit_length()
    bye_count = bracket_size - count

    # Teams at the front of the supplied ordering
    # receive preliminary-round BYEs.
    bye_teams = teams[:bye_count]
    playing_teams = teams[bye_count:]

    first_round: list[KnockoutSlot] = []
    match_number = 1

    for index in range(0, len(playing_teams), 2):
        first_round.append(
            KnockoutSlot(
                round_number=1,
                match_number=match_number,
                home_team_id=playing_teams[index],
                away_team_id=playing_teams[index + 1],
                home_source=None,
                away_source=None,
            )
        )

        match_number += 1

    all_slots = first_round[:]

    advancing: list[
        tuple[str | None, str | None]
    ] = [
        (team, None)
        for team in bye_teams
    ] + [
        (
            None,
            f"winner:{slot.match_number}",
        )
        for slot in first_round
    ]

    round_number = 2

    while len(advancing) > 1:
        next_advancing: list[tuple[str | None, str | None]] = []

        for index in range(0, len(advancing), 2):
            home, home_source = advancing[index]
            away, away_source = advancing[index + 1]

            slot = KnockoutSlot(
                round_number=round_number,
                match_number=match_number,
                home_team_id=home,
                away_team_id=away,
                home_source=home_source,
                away_source=away_source,
            )

            all_slots.append(slot)

            next_advancing.append(
                (
                    None,
                    f"winner:{match_number}",
                )
            )

            match_number += 1

        advancing = next_advancing
        round_number += 1

    return all_slots


def fixture_summary(pairings: Sequence[Pairing]) -> dict:
    """
    Return a summary of generated round-robin fixtures.
    """
    games = [item for item in pairings if not item.is_bye]
    byes = [item for item in pairings if item.is_bye]

    return {
        "matches": len(games),
        "byes": len(byes),
        "rounds": max(
            (
                item.round_number
                for item in pairings
            ),
            default=0,
        ),
        "legs": max(
            (
                item.leg
                for item in pairings
            ),
            default=0,
        ),
    }
