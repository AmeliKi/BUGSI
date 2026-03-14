from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin
from app.models.user import User
from app.repositories import audit_log_repo
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    response: Response = None,
):
    logs = await audit_log_repo.list_audit_logs(db, offset, limit, action, resource_type)
    total = await audit_log_repo.count_audit_logs(db, action, resource_type)
    response.headers["X-Total-Count"] = str(total)
    return logs
