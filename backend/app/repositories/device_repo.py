import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device import Device
from app.models.device_assignment import DeviceAssignment


async def get_device_by_id(db: AsyncSession, device_id: uuid.UUID) -> Device | None:
    result = await db.execute(select(Device).where(Device.id == device_id))
    return result.scalar_one_or_none()


async def get_device_by_serial(db: AsyncSession, serial_number: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.serial_number == serial_number))
    return result.scalar_one_or_none()


async def get_device_by_api_key_hash(db: AsyncSession, api_key_hash: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.api_key_hash == api_key_hash))
    return result.scalar_one_or_none()


async def get_all_devices(
    db: AsyncSession, offset: int = 0, limit: int = 50, include_inactive: bool = True,
) -> list[Device]:
    query = select(Device).options(selectinload(Device.config), selectinload(Device.ota_deployments))
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))
    result = await db.execute(query.offset(offset).limit(limit).order_by(Device.created_at.desc()))
    return list(result.scalars().all())


async def get_devices_for_user(
    db: AsyncSession, user_id: uuid.UUID, offset: int = 0, limit: int = 50,
    include_inactive: bool = True,
) -> list[Device]:
    query = (
        select(Device)
        .join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.user_id == user_id)
        .options(selectinload(Device.config), selectinload(Device.ota_deployments))
    )
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))
    result = await db.execute(query.offset(offset).limit(limit).order_by(Device.created_at.desc()))
    return list(result.scalars().all())


async def count_devices(db: AsyncSession, include_inactive: bool = True) -> int:
    query = select(func.count(Device.id))
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))
    result = await db.execute(query)
    return result.scalar_one()


async def count_devices_for_user(
    db: AsyncSession, user_id: uuid.UUID, include_inactive: bool = True,
) -> int:
    query = (
        select(func.count(Device.id))
        .join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.user_id == user_id)
    )
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))
    result = await db.execute(query)
    return result.scalar_one()


async def create_device(db: AsyncSession, device: Device) -> Device:
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


async def update_device(db: AsyncSession, device: Device, updates: dict) -> Device:
    for key, value in updates.items():
        if value is not None:
            setattr(device, key, value)
    await db.flush()
    await db.refresh(device)
    return device
