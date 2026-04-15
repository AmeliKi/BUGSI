import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, verify_device_access
from app.models.device import Device
from app.models.user import User
from app.schemas.device_config import DeviceConfigResponse, DeviceConfigUpdate
from app.services import config_service
from app.services.default_config import get_default_config, merge_defaults

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/defaults")
async def get_defaults(
    _user: User = Depends(get_current_user),
):
    return get_default_config()


@router.get("/{device_id}", response_model=DeviceConfigResponse)
async def get_config(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_access),
):
    config = await config_service.get_or_create_config(db, device_id)
    # Merge defaults so newly added fields are always visible in the UI
    config.config_json = merge_defaults(config.config_json)
    return config


@router.put("/{device_id}", response_model=DeviceConfigResponse)
async def update_config(
    device_id: uuid.UUID,
    data: DeviceConfigUpdate,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_access),
    user: User = Depends(get_current_user),
):
    return await config_service.update_config(db, device_id, data.config_json, user.id)
