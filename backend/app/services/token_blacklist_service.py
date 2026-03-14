from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blacklisted_token import BlacklistedToken


async def blacklist_token(db: AsyncSession, jti: str, token_type: str, expires_at: datetime) -> None:
    token = BlacklistedToken(jti=jti, token_type=token_type, expires_at=expires_at)
    db.add(token)
    await db.flush()


async def is_token_blacklisted(db: AsyncSession, jti: str) -> bool:
    result = await db.execute(
        select(BlacklistedToken.id).where(BlacklistedToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """Remove expired blacklist entries (can be called periodically)."""
    from sqlalchemy import delete

    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(BlacklistedToken).where(BlacklistedToken.expires_at < now)
    )
    await db.flush()
    return result.rowcount
