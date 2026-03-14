import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.models.device_assignment import DeviceAssignment
from app.models.user import User
from app.repositories import user_repo
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import hash_password, verify_password


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    existing = await user_repo.get_user_by_email(db, data.email)
    if existing:
        raise ConflictError("User with this email already exists")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    return await user_repo.create_user(db, user)


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await user_repo.get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")
    return user


async def list_users(db: AsyncSession, offset: int = 0, limit: int = 50) -> tuple[list[User], int]:
    users = await user_repo.get_all_users(db, offset, limit)
    total = await user_repo.count_users(db)
    return users, total


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = await get_user(db, user_id)
    updates = data.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] != user.email:
        existing = await user_repo.get_user_by_email(db, updates["email"])
        if existing:
            raise ConflictError("Email already in use")

    return await user_repo.update_user(db, user, updates)


async def deactivate_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await get_user(db, user_id)
    return await user_repo.update_user(db, user, {"is_active": False})


async def change_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("Current password is incorrect")
    user.password_hash = hash_password(new_password)
    await db.flush()


async def reset_password(db: AsyncSession, user_id: uuid.UUID, new_password: str) -> User:
    user = await get_user(db, user_id)
    user.password_hash = hash_password(new_password)
    await db.flush()
    await db.refresh(user)
    return user


async def set_device_assignments(
    db: AsyncSession, user_id: uuid.UUID, device_ids: list[uuid.UUID]
) -> None:
    from sqlalchemy import delete, select

    user = await get_user(db, user_id)

    # Remove existing assignments
    await db.execute(delete(DeviceAssignment).where(DeviceAssignment.user_id == user_id))

    # Create new assignments
    for device_id in device_ids:
        assignment = DeviceAssignment(user_id=user_id, device_id=device_id)
        db.add(assignment)

    await db.flush()


async def get_user_device_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    from sqlalchemy import select

    result = await db.execute(
        select(DeviceAssignment.device_id).where(DeviceAssignment.user_id == user_id)
    )
    return list(result.scalars().all())
