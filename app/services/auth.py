from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthConfig, Settings, auth_config, settings
from app.models import LoginAttempt, User, UserSession
from app.security import hash_session_id, new_session_id


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


def attempt_key(name: str) -> str:
    return " ".join(name.split()).casefold()[:50]


def _now() -> datetime:
    return datetime.now(UTC)


async def _blocked_for(db: AsyncSession, column, value: str, now: datetime, config: AuthConfig) -> int:
    window = timedelta(minutes=config.login_window_minutes)
    times = list(
        await db.scalars(
            select(LoginAttempt.created_at)
            .where(column == value, LoginAttempt.created_at > now - window)
            .order_by(LoginAttempt.created_at)
        )
    )
    if len(times) < config.login_max_failures:
        return 0
    release = times[len(times) - config.login_max_failures] + window
    return max(1, int((release - now).total_seconds()) + 1)


async def check_login_allowed(
    db: AsyncSession, name: str, ip: str, now: datetime | None = None, config: AuthConfig = auth_config
) -> None:
    now = now or _now()
    wait = max(
        await _blocked_for(db, LoginAttempt.name, attempt_key(name), now, config),
        await _blocked_for(db, LoginAttempt.ip, ip, now, config),
    )
    if wait:
        raise TooManyAttempts(wait)


async def record_failure(db: AsyncSession, name: str, ip: str, now: datetime | None = None) -> None:
    now = now or _now()
    db.add(LoginAttempt(name=attempt_key(name), ip=ip, created_at=now))
    await db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < now - timedelta(days=1)))
    await db.commit()


async def clear_failures(db: AsyncSession, name: str) -> None:
    await db.execute(delete(LoginAttempt).where(LoginAttempt.name == attempt_key(name)))


async def issue_session(db: AsyncSession, user: User, config: Settings = settings, now: datetime | None = None) -> str:
    now = now or _now()
    session_id, digest = new_session_id()
    await db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.add(UserSession(session_hash=digest, user_id=user.id, expires_at=now + timedelta(days=config.session_ttl_days)))
    return session_id


async def revoke_session(db: AsyncSession, session_id: str | None) -> None:
    if session_id:
        await db.execute(delete(UserSession).where(UserSession.session_hash == hash_session_id(session_id)))


async def user_by_session(db: AsyncSession, session_id: str, now: datetime | None = None) -> User | None:
    return await db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.session_hash == hash_session_id(session_id), UserSession.expires_at > (now or _now()))
    )
