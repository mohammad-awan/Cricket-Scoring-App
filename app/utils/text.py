from __future__ import annotations
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit



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


# Elements whose text content is never shown to people.
_INVISIBLE_ELEMENTS = frozenset({"script", "style", "template", "noscript", "iframe", "object"})


class _TextExtractor(HTMLParser):
    """Keeps text content and drops every tag, attribute and comment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _INVISIBLE_ELEMENTS:
            self._hidden_depth += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _INVISIBLE_ELEMENTS and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def sanitize_plain_text(value: str | None) -> str | None:
    """Reduce user-supplied rich text to safe plain text.

    Markup is removed (its text is kept), control characters other than
    newlines and tabs are dropped, and runs of blank lines are collapsed.
    Display code still escapes the result.
    """

    if value is None:
        return None

    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character
        for character in text
        if character in "\n\t" or unicodedata.category(character)[0] != "C"
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text or None


def validate_http_url(value: str | None) -> str | None:
    """Accept only absolute http(s) URLs, so links are safe to render."""

    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    if any(character.isspace() for character in value):
        raise ValueError("Website must not contain spaces")

    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Website must be an http:// or https:// address")

    return value


_EMAIL_PATTERN = re.compile(r"^[^@\s<>\"']+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()\-.]{3,38}$")


def validate_email(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    if not _EMAIL_PATTERN.match(value):
        raise ValueError("Contact email is not a valid email address")

    return value


def validate_phone(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    if not _PHONE_PATTERN.match(value):
        raise ValueError(
            "Contact phone may contain digits, spaces, "
            "brackets, dashes and a leading +"
        )

    return value
