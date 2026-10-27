import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.config import scheduler_config, settings
from app.db import get_db
from app.enums import Role
from app.models import AuthToken, User
from app.schemas.auth import LoginIn, LoginOut

router = APIRouter(prefix="/auth", tags=["auth"])


def teacher_password_ok(password: str | None) -> bool:
    if not settings.teacher_password or password is None:
        return False
    return secrets.compare_digest(password.encode(), settings.teacher_password.encode())


@router.post("/login", response_model=LoginOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.name == data.name))

    if data.role == Role.TEACHER:
        if not teacher_password_ok(data.password):
            raise HTTPException(403, "Wrong teacher password")
        if user is not None and user.role != Role.TEACHER:
            raise HTTPException(409, "This name is taken by a student")
    elif user is not None and user.role == Role.TEACHER:
        raise HTTPException(403, "This name belongs to a teacher")

    if user is None:
        user = User(name=data.name, role=data.role.value, new_cards_per_day=scheduler_config.new_cards_per_day)
        db.add(user)
        await db.flush()

    token = AuthToken(token=secrets.token_urlsafe(32), user_id=user.id)
    db.add(token)
    await db.commit()
    return LoginOut(token=token.token, name=user.name, role=Role(user.role))


@router.get("/me", response_model=LoginOut)
async def me(user: User = Depends(current_user)):
    return LoginOut(token="", name=user.name, role=Role(user.role))
