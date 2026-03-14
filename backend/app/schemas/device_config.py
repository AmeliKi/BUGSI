import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator

MAX_CONFIG_JSON_SIZE = 64 * 1024  # 64 KB


class DeviceConfigUpdate(BaseModel):
    config_json: dict[str, Any]

    @model_validator(mode="after")
    def validate_config_size(self):
        serialized = json.dumps(self.config_json)
        if len(serialized) > MAX_CONFIG_JSON_SIZE:
            raise ValueError(f"config_json exceeds maximum size of {MAX_CONFIG_JSON_SIZE // 1024} KB")
        return self


class DeviceConfigResponse(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    config_json: dict[str, Any]
    version: int
    last_acked_version: int
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceConfigPollResponse(BaseModel):
    version: int
    config: dict[str, Any]
    has_update: bool


class ConfigAckRequest(BaseModel):
    version: int


class DeviceConfigPushRequest(BaseModel):
    config: dict[str, Any]
    version: int

    @model_validator(mode="after")
    def validate_push_size(self):
        serialized = json.dumps(self.config)
        if len(serialized) > MAX_CONFIG_JSON_SIZE:
            raise ValueError(f"config exceeds maximum size of {MAX_CONFIG_JSON_SIZE // 1024} KB")
        return self


class DeviceConfigPushResponse(BaseModel):
    version: int
    accepted: bool
