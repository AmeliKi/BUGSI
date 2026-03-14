import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: str | uuid.UUID) -> User | None:
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_all_users(db: AsyncSession, offset: int = 0, limit: int = 50) -> list[User]:
    result = await db.execute(select(User).offset(offset).limit(limit).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def count_users(db: AsyncSession) -> int:
    from sqlalchemy import func

    result = await db.execute(select(func.count(User.id)))
    return result.scalar_one()


async def create_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, updates: dict) -> User:
    for key, value in updates.items():
        if value is not None:
            setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user
