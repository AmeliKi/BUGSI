import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thumbnail import Thumbnail


async def create_thumbnail(db: AsyncSession, thumbnail: Thumbnail) -> Thumbnail:
    db.add(thumbnail)
    await db.flush()
    await db.refresh(thumbnail)
    return thumbnail


async def get_thumbnail_by_id(db: AsyncSession, thumbnail_id: uuid.UUID) -> Thumbnail | None:
    result = await db.execute(select(Thumbnail).where(Thumbnail.id == thumbnail_id))
    return result.scalar_one_or_none()


async def get_thumbnails(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[Thumbnail]:
    query = select(Thumbnail).where(Thumbnail.device_id == device_id)
    if from_ts:
        query = query.where(Thumbnail.timestamp >= from_ts)
    if to_ts:
        query = query.where(Thumbnail.timestamp <= to_ts)
    query = query.order_by(Thumbnail.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_thumbnails(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> int:
    query = select(func.count(Thumbnail.id)).where(Thumbnail.device_id == device_id)
    if from_ts:
        query = query.where(Thumbnail.timestamp >= from_ts)
    if to_ts:
        query = query.where(Thumbnail.timestamp <= to_ts)
    result = await db.execute(query)
    return result.scalar_one()


async def delete_thumbnail(db: AsyncSession, thumbnail: Thumbnail) -> None:
    await db.delete(thumbnail)
    await db.flush()
