import uuid
from datetime import datetime

from pydantic import BaseModel


class DeviceCreate(BaseModel):
    name: str
    serial_number: str
    location_lat: float | None = None
    location_lon: float | None = None
    location_description: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    location_description: str | None = None
    is_active: bool | None = None


class DeviceResponse(BaseModel):
    id: uuid.UUID
    name: str
    serial_number: str
    api_key_prefix: str
    location_lat: float | None
    location_lon: float | None
    location_description: str | None
    firmware_version: str | None
    last_seen_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    has_config_pending: bool = False
    has_ota_pending: bool = False

    model_config = {"from_attributes": True}


class DeviceCreateResponse(DeviceResponse):
    api_key: str  # Only returned once on creation
