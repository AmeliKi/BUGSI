import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin
from app.models.user import User
from app.schemas.user import PasswordReset, UserCreate, UserDeviceAssignment, UserResponse, UserUpdate
from app.services import user_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    response: Response = None,
):
    users, total = await user_service.list_users(db, offset, limit)
    response.headers["X-Total-Count"] = str(total)
    return users


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    user = await user_service.create_user(db, data)
    await log_action(db, "create", "user", resource_id=str(user.id), actor_id=_admin.id, actor_email=_admin.email)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    user = await user_service.update_user(db, user_id, data)
    await log_action(db, "update", "user", resource_id=str(user_id), actor_id=_admin.id, actor_email=_admin.email)
    return user


@router.delete("/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    user = await user_service.deactivate_user(db, user_id)
    await log_action(db, "deactivate", "user", resource_id=str(user_id), actor_id=_admin.id, actor_email=_admin.email)
    return user


@router.post("/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: uuid.UUID,
    data: PasswordReset,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    await user_service.reset_password(db, user_id, data.new_password)


@router.get("/{user_id}/devices", response_model=list[uuid.UUID])
async def get_user_devices(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return await user_service.get_user_device_ids(db, user_id)


@router.put("/{user_id}/devices", status_code=204)
async def set_user_devices(
    user_id: uuid.UUID,
    data: UserDeviceAssignment,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    await user_service.set_device_assignments(db, user_id, data.device_ids)
