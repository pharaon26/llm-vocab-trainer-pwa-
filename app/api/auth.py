from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, current_user
from app.config import scheduler_config, settings
from app.db import get_db
from app.enums import Role
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, RegisterIn
from app.security import check_password_async, hash_password_async
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def start_session(response: Response, session_id: str) -> None:
    response.set_cookie(
        settings.session_cookie_name, session_id, max_age=settings.session_ttl_days * 86400,
        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/",
    )


def end_session(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )


def too_many(exc: auth_service.TooManyAttempts) -> HTTPException:
    return HTTPException(
        429, "Too many failed login attempts, try again later", headers={"Retry-After": str(exc.retry_after)}
    )


def find_user(name: str):
    return select(User).where(func.lower(User.name) == name.lower())


@router.post("/register", response_model=LoginOut, status_code=201)
async def register(data: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(User.id).where(func.lower(User.name) == data.name.lower())) is not None:
        raise HTTPException(409, "This nickname is already taken")
    user = User(
        name=data.name, role=data.role.value, new_cards_per_day=scheduler_config.new_cards_per_day,
        password_hash=await hash_password_async(data.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "This nickname is already taken")
    await auth_service.revoke_session(db, request.cookies.get(settings.session_cookie_name))
    session_id = await auth_service.issue_session(db, user)
    await db.commit()
    start_session(response, session_id)
    return LoginOut(name=user.name, role=Role(user.role))


@router.post("/login", response_model=LoginOut)
async def login(data: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip = client_ip(request)
    try:
        await auth_service.check_login_allowed(db, data.name, ip)
    except auth_service.TooManyAttempts as exc:
        raise too_many(exc)

    user = await db.scalar(find_user(data.name))
    if not await check_password_async(data.password or "", user.password_hash if user is not None else None):
        await auth_service.record_failure(db, data.name, ip)
        raise HTTPException(401, "Invalid nickname or password")

    await auth_service.clear_failures(db, data.name)
    await auth_service.revoke_session(db, request.cookies.get(settings.session_cookie_name))
    session_id = await auth_service.issue_session(db, user)
    await db.commit()
    start_session(response, session_id)
    return LoginOut(name=user.name, role=Role(user.role))


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    await auth_service.revoke_session(db, request.cookies.get(settings.session_cookie_name))
    await db.commit()
    response = Response(status_code=204)
    end_session(response)
    return response


@router.get("/me", response_model=LoginOut)
async def me(user: User = Depends(current_user)):
    return LoginOut(name=user.name, role=Role(user.role))
