from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def list_audit_logs(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 50,
    action: str | None = None,
    resource_type: str | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_audit_logs(
    db: AsyncSession,
    action: str | None = None,
    resource_type: str | None = None,
) -> int:
    stmt = select(func.count(AuditLog.id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    result = await db.execute(stmt)
    return result.scalar_one()
