import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models.device import Device
from app.repositories import device_repo
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services import config_service
from app.services.auth_service import generate_api_key


def _to_response(device: Device) -> DeviceResponse:
    has_config_pending = False
    if device.config is not None:
        has_config_pending = device.config.version > device.config.last_acked_version

    has_ota_pending = any(d.status == "pending" for d in device.ota_deployments)

    resp = DeviceResponse.model_validate(device)
    resp.has_config_pending = has_config_pending
    resp.has_ota_pending = has_ota_pending
    return resp


async def create_device(db: AsyncSession, data: DeviceCreate) -> tuple[Device, str]:
    """Create a device and return (device, plaintext_api_key)."""
    existing = await device_repo.get_device_by_serial(db, data.serial_number)
    if existing:
        raise ConflictError("Device with this serial number already exists")

    plaintext_key, key_hash, key_prefix = generate_api_key()

    device = Device(
        name=data.name,
        serial_number=data.serial_number,
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
        location_lat=data.location_lat,
        location_lon=data.location_lon,
        location_description=data.location_description,
    )
    device = await device_repo.create_device(db, device)
    await config_service.get_or_create_config(db, device.id)
    return device, plaintext_key


async def get_device(db: AsyncSession, device_id: uuid.UUID) -> Device:
    device = await device_repo.get_device_by_id(db, device_id)
    if not device:
        raise NotFoundError("Device not found")
    return device


async def list_devices(
    db: AsyncSession, user_id: uuid.UUID | None = None, role: str = "admin",
    offset: int = 0, limit: int = 50, include_inactive: bool = True,
) -> tuple[list[DeviceResponse], int]:
    if role == "admin" or user_id is None:
        devices = await device_repo.get_all_devices(db, offset, limit, include_inactive=include_inactive)
        total = await device_repo.count_devices(db, include_inactive=include_inactive)
    else:
        devices = await device_repo.get_devices_for_user(db, user_id, offset, limit, include_inactive=include_inactive)
        total = await device_repo.count_devices_for_user(db, user_id, include_inactive=include_inactive)
    return [_to_response(d) for d in devices], total


async def update_device(db: AsyncSession, device_id: uuid.UUID, data: DeviceUpdate) -> Device:
    device = await get_device(db, device_id)
    updates = data.model_dump(exclude_unset=True)
    return await device_repo.update_device(db, device, updates)


async def deactivate_device(db: AsyncSession, device_id: uuid.UUID) -> Device:
    from datetime import datetime, timezone

    device = await get_device(db, device_id)
    return await device_repo.update_device(
        db, device, {"is_active": False, "deactivated_at": datetime.now(timezone.utc)}
    )


async def activate_device(db: AsyncSession, device_id: uuid.UUID) -> Device:
    device = await get_device(db, device_id)
    device.is_active = True
    device.deactivated_at = None
    await db.flush()
    await db.refresh(device)
    return device


async def regenerate_api_key(db: AsyncSession, device_id: uuid.UUID) -> tuple[Device, str]:
    device = await get_device(db, device_id)
    plaintext_key, key_hash, key_prefix = generate_api_key()
    device = await device_repo.update_device(
        db, device, {"api_key_hash": key_hash, "api_key_prefix": key_prefix}
    )
    return device, plaintext_key
