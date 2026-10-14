"""Stage 11 player eligibility rules for tournament rosters and XIs.

Pure functions only: services load players and pass plain values in.
"""

from __future__ import annotations
from collections.abc import Iterable
from datetime import date
from app.domain.tournament_rules import EligibilityPolicy


def age_on(date_of_birth: date, on: date) -> int:
    """Completed years of age on a given date."""

    before_birthday = (on.month, on.day) < (date_of_birth.month, date_of_birth.day)
    return on.year - date_of_birth.year - int(before_birthday)


def is_overseas(nationality: str | None, home_nationality: str | None) -> bool:
    if home_nationality is None or nationality is None:
        return False

    return nationality.strip().casefold() != home_nationality.strip().casefold()


def player_eligibility_errors(
    *,
    label: str,
    date_of_birth: date | None,
    sex: str | None,
    nationality: str | None,
    policy: EligibilityPolicy,
    reference_date: date,
    overseas_limit_active: bool,
) -> list[str]:
    """Reasons a player may not join a tournament roster under the policy."""

    errors = []

    if policy.has_age_limit:
        if date_of_birth is None:
            errors.append(f"{label} needs a date of birth for the age limit")
        else:
            age = age_on(date_of_birth, reference_date)

            if policy.minimum_age is not None and age < policy.minimum_age:
                errors.append(
                    f"{label} is {age}; minimum age is {policy.minimum_age} "
                    f"on {reference_date.isoformat()}"
                )

            if policy.maximum_age is not None and age > policy.maximum_age:
                errors.append(
                    f"{label} is {age}; maximum age is {policy.maximum_age} "
                    f"on {reference_date.isoformat()}"
                )

    if policy.sex != "open":
        if sex is None:
            errors.append(f"{label} has no recorded sex for a {policy.sex}-only competition")
        elif sex != policy.sex:
            errors.append(f"{label} is not eligible for a {policy.sex}-only competition")

    if overseas_limit_active and not (nationality and nationality.strip()):
        errors.append(f"{label} needs a nationality for the overseas player limit")

    return errors


def overseas_count(nationalities: Iterable[str | None], home_nationality: str | None) -> int:
    return sum(1 for item in nationalities if is_overseas(item, home_nationality))


def eligibility_reference_date(
    policy: EligibilityPolicy,
    tournament_start: date | None,
    today: date,
) -> date:
    return policy.age_reference_date or tournament_start or today
