import hmac
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Cookie, Depends, Header, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.models.device import Device
from app.models.device_assignment import DeviceAssignment
from app.models.user import User
from app.services.auth_service import decode_token, hash_api_key
from app.services.token_blacklist_service import is_token_blacklisted

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def _resolve_user(token: str | None, db: AsyncSession) -> User:
    if token is None:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except UnauthorizedError:
        raise
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token")
    except (ValueError, KeyError):
        raise UnauthorizedError("Malformed token payload")

    jti = payload.get("jti")
    if jti and await is_token_blacklisted(db, jti):
        raise UnauthorizedError("Token has been revoked")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    access_token_cookie: str | None = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Prefer Authorization header, fall back to httpOnly cookie
    return await _resolve_user(token or access_token_cookie, db)


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ForbiddenError("Admin access required")
    return user


async def get_device_from_api_key(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Device:
    key_prefix = x_api_key[:8]
    key_hash = hash_api_key(x_api_key)

    # Look up by prefix, then compare full hash in constant time
    result = await db.execute(
        select(Device).where(Device.api_key_prefix == key_prefix)
    )
    device = result.scalar_one_or_none()

    if device is None or not hmac.compare_digest(device.api_key_hash, key_hash) or not device.is_active:
        raise UnauthorizedError("Invalid API key")

    # Update last_seen_at
    device.last_seen_at = datetime.now(timezone.utc)
    await db.flush()

    return device


async def verify_device_access(
    device_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundError("Device not found")

    if user.role == "admin":
        return device

    # Check assignment for regular users
    result = await db.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.user_id == user.id,
            DeviceAssignment.device_id == device_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ForbiddenError("Access denied to this device")

    return device


async def verify_device_access_with_query_token(
    device_id: uuid.UUID,
    token: str | None = Depends(oauth2_scheme),
    access_token_cookie: str | None = Cookie(None, alias="access_token"),
    query_token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Like verify_device_access but also accepts token via cookie or query param (for img tags)."""
    user = await _resolve_user(token or access_token_cookie or query_token, db)

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundError("Device not found")

    if user.role == "admin":
        return device

    result = await db.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.user_id == user.id,
            DeviceAssignment.device_id == device_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ForbiddenError("Access denied to this device")

    return device
