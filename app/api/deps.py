from datetime import date

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.enums import Role
from app.models import AuthToken, User

bearer = HTTPBearer(auto_error=False)


def get_today() -> date:
    return date.today()


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    token = await db.get(AuthToken, credentials.credentials)
    if token is None:
        raise HTTPException(401, "Invalid token")
    return await db.get(User, token.user_id)


async def require_teacher(user: User = Depends(current_user)) -> User:
    if user.role != Role.TEACHER:
        raise HTTPException(403, "Teacher role required")
    return user
