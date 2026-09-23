from __future__ import annotations
import re



def clean_required(value: str) -> str:
    return value.strip()


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def slugify(value: str) -> str:
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.strip().lower()
    )

    slug = slug.strip("-")

    if not slug:
        raise ValueError("A non-empty Slug could not be generated")

    return slug[:180].rstrip("-")


