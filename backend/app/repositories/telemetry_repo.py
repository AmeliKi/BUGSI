import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import TelemetryReading


async def create_readings(db: AsyncSession, readings: list[TelemetryReading]) -> list[TelemetryReading]:
    db.add_all(readings)
    await db.flush()
    return readings


async def get_readings(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[TelemetryReading]:
    query = select(TelemetryReading).where(TelemetryReading.device_id == device_id)
    if from_ts:
        query = query.where(TelemetryReading.timestamp >= from_ts)
    if to_ts:
        query = query.where(TelemetryReading.timestamp <= to_ts)
    query = query.order_by(TelemetryReading.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_readings(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> int:
    query = select(func.count(TelemetryReading.id)).where(TelemetryReading.device_id == device_id)
    if from_ts:
        query = query.where(TelemetryReading.timestamp >= from_ts)
    if to_ts:
        query = query.where(TelemetryReading.timestamp <= to_ts)
    result = await db.execute(query)
    return result.scalar_one()
