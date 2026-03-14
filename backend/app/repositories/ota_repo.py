import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ota_deployment import OtaDeployment
from app.models.ota_package import OtaPackage


async def get_package_by_id(db: AsyncSession, package_id: uuid.UUID) -> OtaPackage | None:
    result = await db.execute(select(OtaPackage).where(OtaPackage.id == package_id))
    return result.scalar_one_or_none()


async def get_package_by_version(db: AsyncSession, version: str) -> OtaPackage | None:
    result = await db.execute(select(OtaPackage).where(OtaPackage.version == version))
    return result.scalar_one_or_none()


async def get_all_packages(db: AsyncSession, offset: int = 0, limit: int = 50) -> list[OtaPackage]:
    result = await db.execute(
        select(OtaPackage).offset(offset).limit(limit).order_by(OtaPackage.created_at.desc())
    )
    return list(result.scalars().all())


async def count_packages(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(OtaPackage.id)))
    return result.scalar_one()


async def create_package(db: AsyncSession, package: OtaPackage) -> OtaPackage:
    db.add(package)
    await db.flush()
    await db.refresh(package)
    return package


async def delete_package(db: AsyncSession, package: OtaPackage) -> None:
    await db.delete(package)
    await db.flush()


async def get_deployment_by_id(db: AsyncSession, deployment_id: uuid.UUID) -> OtaDeployment | None:
    result = await db.execute(select(OtaDeployment).where(OtaDeployment.id == deployment_id))
    return result.scalar_one_or_none()


async def get_deployments(
    db: AsyncSession,
    device_id: uuid.UUID | None = None,
    status: str | None = None,
    package_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[OtaDeployment]:
    query = select(OtaDeployment)
    if device_id:
        query = query.where(OtaDeployment.device_id == device_id)
    if status:
        query = query.where(OtaDeployment.status == status)
    if package_id:
        query = query.where(OtaDeployment.ota_package_id == package_id)
    query = query.order_by(OtaDeployment.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_deployments(
    db: AsyncSession,
    device_id: uuid.UUID | None = None,
    status: str | None = None,
    package_id: uuid.UUID | None = None,
) -> int:
    query = select(func.count(OtaDeployment.id))
    if device_id:
        query = query.where(OtaDeployment.device_id == device_id)
    if status:
        query = query.where(OtaDeployment.status == status)
    if package_id:
        query = query.where(OtaDeployment.ota_package_id == package_id)
    result = await db.execute(query)
    return result.scalar_one()


async def get_pending_deployment_for_device(
    db: AsyncSession, device_id: uuid.UUID
) -> OtaDeployment | None:
    result = await db.execute(
        select(OtaDeployment)
        .where(OtaDeployment.device_id == device_id, OtaDeployment.status == "pending")
        .order_by(OtaDeployment.assigned_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_deployment(db: AsyncSession, deployment: OtaDeployment) -> OtaDeployment:
    db.add(deployment)
    await db.flush()
    await db.refresh(deployment)
    return deployment
