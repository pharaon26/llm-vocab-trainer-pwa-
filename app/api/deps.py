from datetime import date

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.enums import Role
from app.models import User
from app.security import resolve_client_ip
from app.services.auth import user_by_session

session_cookie = APIKeyCookie(name=settings.session_cookie_name, auto_error=False)


def get_today() -> date:
    return date.today()


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), settings.trusted_proxies)


async def current_user(
    session_id: str | None = Depends(session_cookie),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not session_id:
        raise HTTPException(401, "Authentication required")
    user = await user_by_session(db, session_id)
    if user is None:
        raise HTTPException(401, "Invalid or expired session")
    return user


async def require_teacher(user: User = Depends(current_user)) -> User:
    if user.role != Role.TEACHER:
        raise HTTPException(403, "Teacher role required")
    return user


async def require_student(user: User = Depends(current_user)) -> User:
    if user.role != Role.STUDENT:
        raise HTTPException(403, "Student role required")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(403, "Administrator role required")
    return user
