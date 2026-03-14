import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=json.dumps(details) if details else None,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "AUDIT: %s %s/%s by %s",
        action,
        resource_type,
        resource_id or "-",
        actor_email or actor_id or "system",
    )
