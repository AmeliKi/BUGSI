import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_admin
from app.exceptions import PayloadTooLargeError, ValidationError
from app.models.user import User
from app.schemas.ota import (
    OtaBuildRequest,
    OtaDeploymentResponse,
    OtaDeployRequest,
    OtaPackageResponse,
)
from app.services import ota_service
from app.services.audit_service import log_action
from app.services.ota_package_builder import PackageBuildError, build_package_from_git

router = APIRouter(prefix="/api/ota", tags=["ota"])

VALID_PACKAGE_TYPES = {"full", "daemon_only", "config_only", "detector_only"}


@router.get("/packages", response_model=list[OtaPackageResponse])
async def list_packages(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    response: Response = None,
):
    packages, total = await ota_service.list_packages(db, offset, limit)
    response.headers["X-Total-Count"] = str(total)
    return packages


@router.post("/packages", response_model=OtaPackageResponse, status_code=201)
async def upload_package(
    file: UploadFile = File(...),
    version: str = Form(...),
    package_type: str = Form(...),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if package_type not in VALID_PACKAGE_TYPES:
        raise ValidationError(
            f"Invalid package_type: '{package_type}'. Must be one of {VALID_PACKAGE_TYPES}"
        )
    file_data = await file.read()
    if len(file_data) > settings.MAX_OTA_PACKAGE_SIZE_BYTES:
        raise PayloadTooLargeError(
            f"OTA package exceeds maximum size of {settings.MAX_OTA_PACKAGE_SIZE_BYTES // (1024 * 1024)} MB"
        )
    package = await ota_service.create_package(db, version, description, package_type, file_data, admin.id)
    await log_action(db, "upload", "ota_package", resource_id=str(package.id), actor_id=admin.id, actor_email=admin.email)
    return package


@router.post("/packages/build", response_model=OtaPackageResponse, status_code=201)
async def build_package(
    data: OtaBuildRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        file_data, manifest = build_package_from_git(
            repo_url=settings.GIT_REPO_URL,
            commit_id=data.commit_id,
            package_type=data.package_type,
            device_code_path=settings.GIT_DEVICE_CODE_PATH,
            config_path=settings.GIT_CONFIG_PATH,
            detector_code_path=settings.GIT_INSECT_DETECTOR_PATH,
            description=data.description,
            version=data.version,
        )
    except PackageBuildError as e:
        raise ValidationError(f"Package build failed: {e.message}")

    if len(file_data) > settings.MAX_OTA_PACKAGE_SIZE_BYTES:
        raise PayloadTooLargeError(
            f"Built package exceeds maximum size of {settings.MAX_OTA_PACKAGE_SIZE_BYTES // (1024 * 1024)} MB"
        )

    version = data.version or data.commit_id[:7]
    package = await ota_service.create_package(
        db, version, data.description or manifest.get("description"),
        data.package_type, file_data, admin.id, commit_id=data.commit_id,
    )
    await log_action(db, "build", "ota_package", resource_id=str(package.id), actor_id=admin.id, actor_email=admin.email)
    return package


@router.get("/packages/{package_id}", response_model=OtaPackageResponse)
async def get_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await ota_service.get_package(db, package_id)


@router.delete("/packages/{package_id}", status_code=204)
async def delete_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    await ota_service.delete_package(db, package_id)
    await log_action(db, "delete", "ota_package", resource_id=str(package_id), actor_id=_admin.id, actor_email=_admin.email)


@router.post("/deploy", response_model=list[OtaDeploymentResponse], status_code=201)
async def deploy(
    data: OtaDeployRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    deployments = await ota_service.create_deployments(db, data.package_id, data.device_ids)
    await log_action(
        db, "deploy", "ota_deployment", resource_id=str(data.package_id),
        actor_id=_admin.id, actor_email=_admin.email,
        details={"device_ids": [str(d) for d in data.device_ids]},
    )
    return deployments


@router.get("/deployments", response_model=list[OtaDeploymentResponse])
async def list_deployments(
    device_id: uuid.UUID | None = None,
    status: str | None = None,
    package_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    response: Response = None,
):
    deployments, total = await ota_service.list_deployments(
        db, device_id, status, package_id, offset, limit
    )
    response.headers["X-Total-Count"] = str(total)
    return deployments


@router.get("/deployments/{deployment_id}", response_model=OtaDeploymentResponse)
async def get_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await ota_service.get_deployment(db, deployment_id)


@router.post("/deployments/{deployment_id}/cancel", response_model=OtaDeploymentResponse)
async def cancel_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await ota_service.cancel_deployment(db, deployment_id)
