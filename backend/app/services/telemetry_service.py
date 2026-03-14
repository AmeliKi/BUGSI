import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import TelemetryReading
from app.repositories import telemetry_repo
from app.schemas.telemetry import TelemetryReadingIn


async def ingest_readings(
    db: AsyncSession, device_id: uuid.UUID, readings_in: list[TelemetryReadingIn]
) -> list[TelemetryReading]:
    readings = [
        TelemetryReading(device_id=device_id, **r.model_dump())
        for r in readings_in
    ]
    return await telemetry_repo.create_readings(db, readings)


async def get_readings(
    db: AsyncSession,
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[TelemetryReading], int]:
    readings = await telemetry_repo.get_readings(db, device_id, from_ts, to_ts, offset, limit)
    total = await telemetry_repo.count_readings(db, device_id, from_ts, to_ts)
    return readings, total
