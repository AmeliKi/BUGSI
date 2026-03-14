import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.models.device_config import DeviceConfig
from app.repositories import device_config_repo
from app.services.default_config import get_default_config, merge_defaults


async def get_config(db: AsyncSession, device_id: uuid.UUID) -> DeviceConfig:
    config = await device_config_repo.get_config_by_device(db, device_id)
    if config is None:
        raise NotFoundError("No config found for device")
    return config


async def get_or_create_config(db: AsyncSession, device_id: uuid.UUID) -> DeviceConfig:
    config = await device_config_repo.get_config_by_device(db, device_id)
    if config is None:
        config = DeviceConfig(
            device_id=device_id,
            config_json=get_default_config(),
            version=1,
            last_acked_version=0,
        )
        config = await device_config_repo.create_config(db, config)
    return config


async def update_config(
    db: AsyncSession,
    device_id: uuid.UUID,
    config_json: dict[str, Any],
    updated_by: uuid.UUID | None = None,
) -> DeviceConfig:
    config = await get_or_create_config(db, device_id)
    config.config_json = merge_defaults(config_json)
    config.version += 1
    config.updated_by = updated_by
    return await device_config_repo.update_config(db, config)


async def poll_config(db: AsyncSession, device_id: uuid.UUID) -> dict:
    config = await get_or_create_config(db, device_id)
    return {
        "version": config.version,
        "config": merge_defaults(config.config_json),
        "has_update": config.version > config.last_acked_version,
    }


async def ack_config(db: AsyncSession, device_id: uuid.UUID, version: int) -> None:
    config = await get_or_create_config(db, device_id)
    if version <= config.version:
        config.last_acked_version = version
        await device_config_repo.update_config(db, config)


async def apply_device_push(
    db: AsyncSession,
    device_id: uuid.UUID,
    config_json: dict[str, Any],
    version: int,
) -> dict:
    """Accept a config push from the device. Returns {version, accepted}."""
    config = await get_or_create_config(db, device_id)

    if version >= config.version:
        config.config_json = merge_defaults(config_json)
        config.version = version
        config.last_acked_version = version
        await device_config_repo.update_config(db, config)
        return {"version": version, "accepted": True}

    return {"version": config.version, "accepted": False}
