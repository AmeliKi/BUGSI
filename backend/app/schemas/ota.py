import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PackageType = Literal["full", "daemon_only", "config_only"]


class OtaPackageResponse(BaseModel):
    id: uuid.UUID
    version: str
    description: str | None
    package_type: str
    file_size_bytes: int
    checksum_sha256: str
    commit_id: str | None
    signature: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OtaBuildRequest(BaseModel):
    commit_id: str
    package_type: PackageType = "full"
    description: str | None = None
    version: str | None = None  # Optional override; defaults to short commit hash


class OtaDeployRequest(BaseModel):
    package_id: uuid.UUID
    device_ids: list[uuid.UUID]


class OtaDeploymentResponse(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    ota_package_id: uuid.UUID
    status: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OtaDeploymentDetail(BaseModel):
    id: uuid.UUID
    package_version: str
    package_type: str
    file_size_bytes: int
    checksum_sha256: str
    signature: str | None = None


class OtaCheckResponse(BaseModel):
    has_update: bool
    deployment: OtaDeploymentDetail | None = None


class OtaStatusReport(BaseModel):
    status: str  # downloading, installing, completed, failed
    error_message: str | None = None
