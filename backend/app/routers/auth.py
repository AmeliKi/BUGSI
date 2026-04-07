from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.exceptions import UnauthorizedError
from app.rate_limit import limiter
from app.models.user import User
from app.telemetry import login_attempts_counter
from app.repositories import user_repo
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.user import ChangePassword, UpdatePreferencesRequest, UserResponse
from app.services import user_service
from app.services.audit_service import log_action
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.token_blacklist_service import blacklist_token, is_token_blacklisted

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/api",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/api")
    response.delete_cookie(key="refresh_token", path="/api/auth/refresh")

# Pre-computed dummy hash so timing is consistent when user doesn't exist
_DUMMY_HASH = hash_password("dummy-password-for-timing")

SUPPORTED_LANGUAGES = ("en", "de")


class UpdateLanguageRequest(BaseModel):
    language: str

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await user_repo.get_user_by_email(db, data.email)
    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_valid = verify_password(data.password, password_hash)
    if user is None or not password_valid:
        login_attempts_counter.add(1, {"success": "false"})
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        login_attempts_counter.add(1, {"success": "false"})
        raise UnauthorizedError("Account is disabled")

    login_attempts_counter.add(1, {"success": "true"})
    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    data: RefreshRequest | None = None,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
):
    # Accept refresh token from cookie or request body
    raw_refresh = refresh_token_cookie or (data.refresh_token if data else None)
    if not raw_refresh:
        raise UnauthorizedError("No refresh token provided")

    try:
        payload = decode_token(raw_refresh)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
    except UnauthorizedError:
        raise
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Refresh token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid refresh token")
    except (ValueError, KeyError):
        raise UnauthorizedError("Malformed refresh token")

    # Check if this refresh token has already been used (rotation)
    old_jti = payload.get("jti")
    if old_jti and await is_token_blacklisted(db, old_jti):
        raise UnauthorizedError("Refresh token has been revoked")

    user = await user_repo.get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    # Blacklist the old refresh token (rotation: each refresh token is single-use)
    if old_jti:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        await blacklist_token(db, old_jti, "refresh", expires_at)

    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(oauth2_scheme),
    access_token_cookie: str | None = Cookie(None, alias="access_token"),
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
):
    """Blacklist the current access and refresh tokens, clear cookies."""
    # Blacklist access token (from header or cookie)
    raw_access = token or access_token_cookie
    if raw_access:
        try:
            payload = decode_token(raw_access)
            jti = payload.get("jti")
            if jti:
                expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                await blacklist_token(db, jti, "access", expires_at)
        except (jwt.InvalidTokenError, KeyError):
            pass

    # Blacklist refresh token (from cookie or body)
    raw_refresh = refresh_token_cookie
    if not raw_refresh:
        try:
            body = await request.json()
            raw_refresh = body.get("refresh_token")
        except Exception:
            pass
    if raw_refresh:
        try:
            payload = decode_token(raw_refresh)
            jti = payload.get("jti")
            if jti:
                expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                await blacklist_token(db, jti, "refresh", expires_at)
        except (jwt.InvalidTokenError, KeyError):
            pass

    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/me/password", status_code=204)
async def change_my_password(
    data: ChangePassword,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await user_service.change_password(db, user, data.current_password, data.new_password)
    await log_action(db, "change_password", "user", resource_id=str(user.id), actor_id=user.id, actor_email=user.email)


@router.patch("/me/language", response_model=UserResponse)
async def update_my_language(
    data: UpdateLanguageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail=f"Language must be one of: {', '.join(SUPPORTED_LANGUAGES)}")
    user.language = data.language
    await db.flush()
    await db.refresh(user)
    return user


VALID_TELEMETRY_FIELDS = {
    "battery_voltage", "battery_soc", "battery_current", "battery_power",
    "battery_consumed_ah", "battery_ttg_min", "temperature", "humidity",
    "lte_signal_strength", "lte_signal_quality", "storage_used_mb",
    "storage_total_mb", "cpu_temp", "uptime_seconds", "pictures_taken",
}


@router.patch("/me/preferences", response_model=UserResponse)
async def update_my_preferences(
    data: UpdatePreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_prefs = data.preferences
    if "hidden_telemetry_fields" in new_prefs:
        hidden = new_prefs["hidden_telemetry_fields"]
        if not isinstance(hidden, list):
            raise HTTPException(status_code=422, detail="hidden_telemetry_fields must be a list")
        invalid = set(hidden) - VALID_TELEMETRY_FIELDS
        if invalid:
            raise HTTPException(status_code=422, detail=f"Invalid telemetry fields: {', '.join(sorted(invalid))}")
    merged = {**(user.preferences or {}), **new_prefs}
    user.preferences = merged
    await db.flush()
    await db.refresh(user)
    return user
