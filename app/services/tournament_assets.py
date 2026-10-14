"""Stage 11 tournament logo and cover images.

Uploads are validated by size and by their actual bytes (PNG, JPEG or
WebP signatures), never by the client's claimed type or filename. SVG is
deliberately not accepted because it can carry script. Files are stored
under application-generated, content-addressed keys; previous uploads
are kept as non-current rows for the audit trail.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.models import TournamentAsset, TournamentStatus
from app.repositories.tournaments import TournamentRepository
from app.schemas.tournaments import TournamentAssetRead
from app.services.storage import LocalObjectStorage, get_object_storage
from app.services.tournaments import (
    _refreshed,
    get_tournament,
    locked_tournament,
    tournament_audit,
    tournament_transaction,
)


ASSET_KINDS = frozenset({"logo", "cover"})

# content type -> file extension
ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def detect_image_type(data: bytes) -> str | None:
    """Content type from the file signature, or None if not allowed."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    return None


def validate_image_upload(
    data: bytes,
    declared_type: str | None,
    max_bytes: int,
) -> str:
    """Return the verified content type or raise a client error."""

    if not data:
        raise ValidationError("The uploaded file is empty")

    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"Images must be {max_bytes // 1024} KB or smaller"
        )

    detected = detect_image_type(data)
    if detected is None:
        raise UnsupportedMediaTypeError("Only PNG, JPEG and WebP images are accepted")

    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared and declared not in {detected, "application/octet-stream"}:
        raise UnsupportedMediaTypeError(
            f"The file is {detected}, not the declared {declared}"
        )

    return detected


def ensure_asset_kind(kind: str) -> None:
    if kind not in ASSET_KINDS:
        raise NotFoundError("Unknown asset kind; use logo or cover")


def asset_url(asset: TournamentAsset) -> str:
    # The version query busts browser caches when the image changes.
    return f"/tournaments/{asset.tournament_id}/assets/{asset.kind}?v={asset.sha256[:12]}"


def asset_read(asset: TournamentAsset) -> TournamentAssetRead:
    return TournamentAssetRead(
        id=asset.id,
        tournament_id=asset.tournament_id,
        kind=asset.kind,
        url=asset_url(asset),
        content_type=asset.content_type,
        byte_size=asset.byte_size,
        sha256=asset.sha256,
        original_filename=asset.original_filename,
        created_at=asset.created_at,
    )


def _safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None

    name = Path(filename.replace("\\", "/")).name.strip()
    return name[:255] or None


async def list_tournament_assets(
    session: AsyncSession,
    tournament_id: UUID,
) -> list[TournamentAssetRead]:
    await get_tournament(session, tournament_id)
    assets = await TournamentRepository(session).current_assets(tournament_id)
    return [asset_read(asset) for asset in assets]


async def upload_tournament_asset(
    session: AsyncSession,
    tournament_id: UUID,
    kind: str,
    data: bytes,
    *,
    declared_type: str | None = None,
    filename: str | None = None,
    actor_id: str | None = None,
    storage: LocalObjectStorage | None = None,
) -> TournamentAssetRead:
    ensure_asset_kind(kind)
    content_type = validate_image_upload(
        data,
        declared_type,
        get_settings().tournament_asset_max_bytes,
    )
    sha256 = hashlib.sha256(data).hexdigest()
    object_key = (
        f"tournaments/{tournament_id}/{kind}-{sha256[:32]}."
        f"{ALLOWED_IMAGE_TYPES[content_type]}"
    )
    storage = storage or get_object_storage()
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament asset"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status == TournamentStatus.ARCHIVED:
            raise ConflictError("Archived tournaments are read-only")

        current = await repository.current_asset(tournament_id, kind)
        if current is not None and current.sha256 == sha256:
            return asset_read(current)

        if current is not None:
            current.is_current = False
            await session.flush()

        # Write the file before committing the row; a failed commit only
        # leaves an unreferenced content-addressed file behind.
        storage.put(object_key, data)

        asset = await repository.asset_by_key(object_key)
        if asset is not None:
            # Re-selecting an image uploaded earlier for this kind.
            asset.is_current = True
        else:
            asset = TournamentAsset(
                tournament_id=tournament_id,
                kind=kind,
                object_key=object_key,
                content_type=content_type,
                byte_size=len(data),
                sha256=sha256,
                original_filename=_safe_filename(filename),
                created_by=actor_id,
                is_current=True,
            )
            session.add(asset)

        await session.flush()

        tournament_audit(
            session,
            tournament_id,
            "asset_uploaded",
            {
                "kind": kind,
                "asset_id": str(asset.id),
                "content_type": content_type,
                "byte_size": len(data),
                "sha256": sha256,
            },
            actor_id=actor_id,
        )

        return asset_read(await _refreshed(session, asset))


async def clear_tournament_asset(
    session: AsyncSession,
    tournament_id: UUID,
    kind: str,
    *,
    actor_id: str | None = None,
) -> dict[str, bool]:
    ensure_asset_kind(kind)
    repository = TournamentRepository(session)

    async with tournament_transaction(session, "Tournament asset"):
        tournament = await locked_tournament(repository, tournament_id)

        if tournament.status == TournamentStatus.ARCHIVED:
            raise ConflictError("Archived tournaments are read-only")

        current = await repository.current_asset(tournament_id, kind)
        if current is None:
            return {"removed": False}

        current.is_current = False

        tournament_audit(
            session,
            tournament_id,
            "asset_removed",
            {"kind": kind, "asset_id": str(current.id)},
            actor_id=actor_id,
        )

        await session.flush()
        return {"removed": True}


async def current_asset_file(
    session: AsyncSession,
    tournament_id: UUID,
    kind: str,
    storage: LocalObjectStorage | None = None,
) -> tuple[Path, TournamentAsset]:
    ensure_asset_kind(kind)
    asset = await TournamentRepository(session).current_asset(tournament_id, kind)
    if asset is None:
        raise NotFoundError(f"This tournament has no {kind}")

    path = (storage or get_object_storage()).path_for(asset.object_key)
    if not path.is_file():
        raise NotFoundError(f"The {kind} file is missing from storage")

    return path, asset
