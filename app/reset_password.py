import argparse
import asyncio
import getpass

from sqlalchemy import delete, func, select

from app.config import auth_config
from app.db import SessionLocal, engine
from app.models import User, UserSession
from app.security import hash_password


async def main(nickname: str, password: str) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(func.lower(User.name) == nickname.lower()))
        if user is None:
            raise SystemExit(f"Пользователь не найден: {nickname}")
        user.password_hash = hash_password(password)
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()
    await engine.dispose()
    print(f"Пароль для {nickname} задан, все его сессии завершены")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сбросить пароль любому пользователю (в том числе созданному до появления паролей)")
    parser.add_argument("nickname")
    args = parser.parse_args()
    password = getpass.getpass("Новый пароль: ")
    if len(password) < auth_config.password_min_length:
        raise SystemExit(f"Пароль короче {auth_config.password_min_length} символов")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    asyncio.run(main(args.nickname, password))
