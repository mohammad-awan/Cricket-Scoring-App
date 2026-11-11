"""Local image uploads for team, player and venue profiles."""
import hashlib
import re
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError
from app.services.storage import get_object_storage
from app.services.tournament_assets import ALLOWED_IMAGE_TYPES, validate_image_upload

router = APIRouter(prefix="/profile-assets", tags=["Profile images"])
Resource = Literal["teams", "players", "venues"]


@router.post("/{resource}", status_code=201)
async def upload_profile_image(resource: Resource, request: Request):
    limit = get_settings().profile_image_max_bytes
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise PayloadTooLargeError(f"Images must be {limit // (1024 * 1024)} MB or smaller")
        data.extend(chunk)
    content = bytes(data)
    content_type = validate_image_upload(content, request.headers.get("content-type"), limit)
    filename = f"{hashlib.sha256(content).hexdigest()}.{ALLOWED_IMAGE_TYPES[content_type]}"
    get_object_storage().put(f"profile-assets/{resource}/{filename}", content)
    return {"url": f"/profile-assets/{resource}/{filename}", "content_type": content_type}


@router.get("/{resource}/{filename}")
async def get_profile_image(resource: Resource, filename: str):
    if not re.fullmatch(r"[a-f0-9]{64}\.(png|jpg|webp)", filename):
        raise NotFoundError("Image not found")
    storage = get_object_storage()
    key = f"profile-assets/{resource}/{filename}"
    if not storage.exists(key):
        raise NotFoundError("Image not found")
    extension = filename.rsplit(".", 1)[1]
    content_type = next(kind for kind, suffix in ALLOWED_IMAGE_TYPES.items() if suffix == extension)
    return FileResponse(storage.path_for(key), media_type=content_type,
                        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})
