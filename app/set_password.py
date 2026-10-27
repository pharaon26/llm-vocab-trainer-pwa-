import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.config import auth_config
from app.db import SessionLocal, engine
from app.enums import Role
from app.models import User
from app.security import hash_password


async def main(name: str, password: str) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.name == name, User.role == Role.STUDENT.value))
        if user is None:
            raise SystemExit(f"Студент не найден: {name}")
        user.password_hash = hash_password(password)
        await db.commit()
    await engine.dispose()
    print(f"Пароль для {name} задан")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Задать пароль существующему студенту (например, созданному до появления паролей)")
    parser.add_argument("name")
    args = parser.parse_args()
    password = getpass.getpass("Новый пароль: ")
    if len(password) < auth_config.password_min_length:
        raise SystemExit(f"Пароль короче {auth_config.password_min_length} символов")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    asyncio.run(main(args.name, password))
