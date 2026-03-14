import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin, get_current_user, verify_device_access, verify_device_access_with_query_token
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceCreateResponse, DeviceResponse, DeviceUpdate
from app.schemas.telemetry import TelemetryReadingOut
from app.schemas.thumbnail import ThumbnailOut
from app.services import device_service, telemetry_service, thumbnail_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_inactive: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    response: Response = None,
):
    devices, total = await device_service.list_devices(
        db, user_id=user.id, role=user.role, offset=offset, limit=limit,
        include_inactive=include_inactive,
    )
    response.headers["X-Total-Count"] = str(total)
    return devices


@router.post("", response_model=DeviceCreateResponse, status_code=201)
async def create_device(
    data: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    device, api_key = await device_service.create_device(db, data)
    return DeviceCreateResponse(
        **DeviceResponse.model_validate(device).model_dump(),
        api_key=api_key,
    )


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device: Device = Depends(verify_device_access),
):
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await device_service.update_device(db, device_id, data)


@router.delete("/{device_id}", response_model=DeviceResponse)
async def deactivate_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    device = await device_service.deactivate_device(db, device_id)
    await log_action(db, "deactivate", "device", resource_id=str(device_id), actor_id=_admin.id, actor_email=_admin.email)
    return device


@router.post("/{device_id}/activate", response_model=DeviceResponse)
async def activate_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    device = await device_service.activate_device(db, device_id)
    await log_action(db, "activate", "device", resource_id=str(device_id), actor_id=_admin.id, actor_email=_admin.email)
    return device


@router.post("/{device_id}/regenerate-key", response_model=DeviceCreateResponse)
async def regenerate_key(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    device, api_key = await device_service.regenerate_api_key(db, device_id)
    await log_action(db, "regenerate_key", "device", resource_id=str(device_id), actor_id=_admin.id, actor_email=_admin.email)
    return DeviceCreateResponse(
        **DeviceResponse.model_validate(device).model_dump(),
        api_key=api_key,
    )


@router.get("/{device_id}/telemetry", response_model=list[TelemetryReadingOut])
async def get_telemetry(
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_access),
    response: Response = None,
):
    readings, total = await telemetry_service.get_readings(db, device_id, from_ts, to_ts, offset, limit)
    response.headers["X-Total-Count"] = str(total)
    return readings


@router.get("/{device_id}/thumbnails", response_model=list[ThumbnailOut])
async def get_thumbnails(
    device_id: uuid.UUID,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_access),
    response: Response = None,
):
    thumbs, total = await thumbnail_service.get_thumbnails(db, device_id, from_ts, to_ts, offset, limit)
    response.headers["X-Total-Count"] = str(total)
    return thumbs


@router.get("/{device_id}/thumbnails/{thumbnail_id}/image")
async def get_thumbnail_image(
    device_id: uuid.UUID,
    thumbnail_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_access_with_query_token),
):
    from fastapi.responses import FileResponse

    file_path = await thumbnail_service.get_thumbnail_file_path(db, thumbnail_id, device_id)
    return FileResponse(file_path, media_type="image/jpeg")
