import hashlib
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.ota_deployment import OtaDeployment
from app.models.ota_package import OtaPackage
from app.repositories import ota_repo
from app.services.ota_package_builder import sign_package
from app.services.ota_package_validator import PackageValidationError, validate_package
from app.telemetry import ota_deployments_counter, upload_size_histogram


def _safe_path(rel_path: str) -> str:
    """Construct an absolute path within UPLOAD_DIR, rejecting traversal attempts."""
    abs_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, rel_path))
    if not abs_path.startswith(os.path.abspath(settings.UPLOAD_DIR) + os.sep):
        raise ForbiddenError("Invalid file path")
    return abs_path


async def create_package(
    db: AsyncSession,
    version: str,
    description: str | None,
    package_type: str,
    file_data: bytes,
    created_by: uuid.UUID | None = None,
    commit_id: str | None = None,
) -> OtaPackage:
    existing = await ota_repo.get_package_by_version(db, version)
    if existing:
        raise ConflictError(f"Package version {version} already exists")

    checksum = hashlib.sha256(file_data).hexdigest()

    try:
        validate_package(file_data, version, package_type)
    except PackageValidationError as e:
        raise ValidationError(f"Invalid OTA package: {e.message}")

    file_id = uuid.uuid4()
    rel_path = f"ota_packages/{file_id}_{version}.tar.gz"
    abs_path = os.path.join(settings.UPLOAD_DIR, rel_path)

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(file_data)

    signature = None
    if settings.OTA_SIGNING_KEY_PATH:
        signature = sign_package(file_data, settings.OTA_SIGNING_KEY_PATH)

    package = OtaPackage(
        version=version,
        description=description,
        package_type=package_type,
        file_path=rel_path,
        file_size_bytes=len(file_data),
        checksum_sha256=checksum,
        commit_id=commit_id,
        signature=signature,
        created_by=created_by,
    )
    result = await ota_repo.create_package(db, package)
    upload_size_histogram.record(len(file_data), {"type": "ota_package"})
    return result


async def get_package(db: AsyncSession, package_id: uuid.UUID) -> OtaPackage:
    package = await ota_repo.get_package_by_id(db, package_id)
    if package is None:
        raise NotFoundError("OTA package not found")
    return package


async def list_packages(
    db: AsyncSession, offset: int = 0, limit: int = 50
) -> tuple[list[OtaPackage], int]:
    packages = await ota_repo.get_all_packages(db, offset, limit)
    total = await ota_repo.count_packages(db)
    return packages, total


async def delete_package(db: AsyncSession, package_id: uuid.UUID) -> None:
    package = await get_package(db, package_id)
    active = await ota_repo.count_deployments(
        db, package_id=package_id, status="pending"
    )
    if active > 0:
        raise ConflictError("Cannot delete package with active deployments")

    # Delete file
    abs_path = _safe_path(package.file_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)

    await ota_repo.delete_package(db, package)


async def create_deployments(
    db: AsyncSession, package_id: uuid.UUID, device_ids: list[uuid.UUID]
) -> list[OtaDeployment]:
    package = await get_package(db, package_id)
    deployments = []
    for device_id in device_ids:
        deployment = OtaDeployment(
            device_id=device_id,
            ota_package_id=package_id,
        )
        deployment = await ota_repo.create_deployment(db, deployment)
        deployments.append(deployment)
    return deployments


async def list_deployments(
    db: AsyncSession,
    device_id: uuid.UUID | None = None,
    status: str | None = None,
    package_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[OtaDeployment], int]:
    deployments = await ota_repo.get_deployments(db, device_id, status, package_id, offset, limit)
    total = await ota_repo.count_deployments(db, device_id, status, package_id)
    return deployments, total


async def get_deployment(db: AsyncSession, deployment_id: uuid.UUID) -> OtaDeployment:
    deployment = await ota_repo.get_deployment_by_id(db, deployment_id)
    if deployment is None:
        raise NotFoundError("OTA deployment not found")
    return deployment


async def cancel_deployment(db: AsyncSession, deployment_id: uuid.UUID) -> OtaDeployment:
    deployment = await get_deployment(db, deployment_id)
    if deployment.status != "pending":
        raise ConflictError("Can only cancel pending deployments")
    deployment.status = "cancelled"
    await db.flush()
    await db.refresh(deployment)
    return deployment


async def check_for_update(db: AsyncSession, device_id: uuid.UUID) -> dict:
    deployment = await ota_repo.get_pending_deployment_for_device(db, device_id)
    if deployment is None:
        return {"has_update": False, "deployment": None}

    package = await ota_repo.get_package_by_id(db, deployment.ota_package_id)
    return {
        "has_update": True,
        "deployment": {
            "id": deployment.id,
            "package_version": package.version,
            "package_type": package.package_type,
            "file_size_bytes": package.file_size_bytes,
            "checksum_sha256": package.checksum_sha256,
            "signature": package.signature,
        },
    }


async def get_package_file_path(db: AsyncSession, deployment_id: uuid.UUID, device_id: uuid.UUID) -> str:
    deployment = await get_deployment(db, deployment_id)
    if deployment.device_id != device_id:
        raise NotFoundError("OTA deployment not found")
    package = await get_package(db, deployment.ota_package_id)
    return _safe_path(package.file_path)


async def update_deployment_status(
    db: AsyncSession, deployment_id: uuid.UUID, status: str, error_message: str | None = None, device_id: uuid.UUID | None = None
) -> OtaDeployment:
    deployment = await get_deployment(db, deployment_id)
    if device_id is not None and deployment.device_id != device_id:
        raise NotFoundError("OTA deployment not found")
    deployment.status = status
    if status in ("downloading", "installing") and deployment.started_at is None:
        deployment.started_at = datetime.now(timezone.utc)
    if status in ("completed", "failed"):
        deployment.completed_at = datetime.now(timezone.utc)
    if error_message:
        deployment.error_message = error_message
    await db.flush()
    await db.refresh(deployment)
    ota_deployments_counter.add(1, {"status": status})
    return deployment
