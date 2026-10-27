import argparse
import asyncio
import getpass
import re

from sqlalchemy import func, select

from app.config import auth_config
from app.db import SessionLocal, engine
from app.enums import Role
from app.models import User
from app.security import hash_password

NICKNAME = re.compile(rf"^[A-Za-z0-9_]{{{auth_config.nickname_min_length},{auth_config.nickname_max_length}}}$")


async def main(nickname: str, password: str) -> None:
    async with SessionLocal() as db:
        if await db.scalar(select(User.id).where(func.lower(User.name) == nickname.lower())) is not None:
            raise SystemExit(f"Ник уже занят: {nickname}")
        db.add(User(name=nickname, role=Role.ADMIN.value, password_hash=hash_password(password)))
        await db.commit()
    await engine.dispose()
    print(f"Администратор {nickname} создан")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создать администратора (управляет общим набором карточек)")
    parser.add_argument("nickname")
    args = parser.parse_args()
    if not NICKNAME.match(args.nickname):
        raise SystemExit("Ник: латиница, цифры и подчеркивание, 3-32 символа")
    password = getpass.getpass("Пароль: ")
    if len(password) < auth_config.password_min_length:
        raise SystemExit(f"Пароль короче {auth_config.password_min_length} символов")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    asyncio.run(main(args.nickname, password))
