import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

KNOWN_BAD_SECRETS = {
    "dev-secret-key-change-in-production",
    "change-this-to-a-random-string-in-production",
    "bugsi-dev-secret-key-2026",
}


def _validate_secret_key(key: str) -> None:
    if key in KNOWN_BAD_SECRETS:
        raise RuntimeError("SECRET_KEY must be changed from the default value")
    if len(key) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters")


def _validate_admin_password(password: str) -> None:
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters")
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_upper and has_lower and has_digit):
        raise RuntimeError("ADMIN_PASSWORD must contain uppercase, lowercase, and digit characters")


async def _seed_or_update_admin(session) -> None:
    """Create the admin user or update credentials if they changed."""
    from app.models.user import User
    from app.services.auth_service import hash_password, verify_password
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.role == "admin").limit(1))
    admin = result.scalar_one_or_none()
    if admin is None:
        admin = User(
            email=settings.ADMIN_EMAIL,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            full_name="Admin",
            role="admin",
        )
        session.add(admin)
        await session.commit()
        logger.info("Default admin user created: %s", settings.ADMIN_EMAIL)
    else:
        updated = False
        if not verify_password(settings.ADMIN_PASSWORD, admin.password_hash):
            admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
            updated = True
            logger.info("Admin password updated for: %s", admin.email)
        if admin.email != settings.ADMIN_EMAIL:
            admin.email = settings.ADMIN_EMAIL
            updated = True
            logger.info("Admin email updated to: %s", settings.ADMIN_EMAIL)
        if updated:
            await session.commit()
        else:
            logger.info("Admin user verified: %s", admin.email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate settings
    _validate_secret_key(settings.SECRET_KEY)
    _validate_admin_password(settings.ADMIN_PASSWORD)

    # Startup: seed admin user or sync credentials if changed
    from app.database import async_session

    async with async_session() as session:
        await _seed_or_update_admin(session)

    # Initialize OpenTelemetry
    from app.telemetry import setup_telemetry

    setup_telemetry(app)

    yield


from app.rate_limit import limiter

app = FastAPI(title="BUGSI Device Management", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        "%s %s status=%d duration=%.3fs",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


from app.routers import audit_logs, auth, config, device_data, devices, ota, users

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(device_data.router)
app.include_router(config.router)
app.include_router(ota.router)
app.include_router(audit_logs.router)


from app.database import get_db


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy"},
        )
