from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Role
from app.models import AuthToken, User

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    token = db.get(AuthToken, credentials.credentials)
    if token is None:
        raise HTTPException(401, "Invalid token")
    return db.get(User, token.user_id)


def require_teacher(user: User = Depends(current_user)) -> User:
    if user.role != Role.TEACHER:
        raise HTTPException(403, "Teacher role required")
    return user
