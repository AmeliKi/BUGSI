import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.thumbnail import Thumbnail
from app.repositories import thumbnail_repo

# JPEG: FF D8 FF, PNG: 89 50 4E 47 0D 0A 1A 0A
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _validate_image_magic_bytes(data: bytes) -> None:
    if data[:3] == _JPEG_MAGIC or data[:8] == _PNG_MAGIC:
        return
    raise ValidationError("Invalid image format: only JPEG and PNG are accepted")


async def save_thumbnail(
    db: AsyncSession,
    device_id: uuid.UUID,
    timestamp: datetime,
    image_data: bytes,
    width: int | None = None,
    height: int | None = None,
) -> Thumbnail:
    _validate_image_magic_bytes(image_data)
    now = datetime.now(timezone.utc)
    rel_dir = f"thumbnails/{device_id}/{now.year}-{now.month:02d}"
    abs_dir = os.path.join(settings.UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    file_id = uuid.uuid4()
    file_name = f"{file_id}.jpg"
    rel_path = f"{rel_dir}/{file_name}"
    abs_path = os.path.join(settings.UPLOAD_DIR, rel_path)

    with open(abs_path, "wb") as f:
        f.write(image_data)

    thumbnail = Thumbnail(
        device_id=device_id,
        timestamp=timestamp,
        file_path=rel_path,
        file_size_bytes=len(image_data),
        width=width,
        height=height,
    )
    return await thumbnail_repo.create_thumbnail(db, thumbnail)


def _safe_path(rel_path: str) -> str:
    """Construct an absolute path within UPLOAD_DIR, rejecting traversal attempts."""
    abs_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, rel_path))
    if not abs_path.startswith(os.path.abspath(settings.UPLOAD_DIR) + os.sep):
        raise ForbiddenError("Invalid file path")
    return abs_path


async def get_thumbnail_file_path(db: AsyncSession, thumbnail_id: uuid.UUID, device_id: uuid.UUID) -> str:
    thumb = await thumbnail_repo.get_thumbnail_by_id(db, thumbnail_id)
    if thumb is None or thumb.device_id != device_id:
        raise NotFoundError("Thumbnail not found")
    return _safe_path(thumb.file_path)


async def delete_thumbnail(db: AsyncSession, thumbnail_id: uuid.UUID) -> None:
    thumb = await thumbnail_repo.get_thumbnail_by_id(db, thumbnail_id)
    if thumb is None:
        raise NotFoundError("Thumbnail not found")
    abs_path = _safe_path(thumb.file_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)
    await thumbnail_repo.delete_thumbnail(db, thumb)


async def get_thumbnails(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Thumbnail], int]:
    thumbs = await thumbnail_repo.get_thumbnails(db, device_id, from_ts, to_ts, offset, limit)
    total = await thumbnail_repo.count_thumbnails(db, device_id, from_ts, to_ts)
    return thumbs, total
