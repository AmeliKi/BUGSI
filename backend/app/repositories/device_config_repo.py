import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_config import DeviceConfig


async def get_config_by_device(db: AsyncSession, device_id: uuid.UUID) -> DeviceConfig | None:
    result = await db.execute(
        select(DeviceConfig).where(DeviceConfig.device_id == device_id)
    )
    return result.scalar_one_or_none()


async def create_config(db: AsyncSession, config: DeviceConfig) -> DeviceConfig:
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def update_config(db: AsyncSession, config: DeviceConfig) -> DeviceConfig:
    await db.flush()
    await db.refresh(config)
    return config
