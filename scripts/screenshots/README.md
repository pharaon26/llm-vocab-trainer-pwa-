# Скриншоты для README

Скрипты не входят в зависимости проекта. Нужны Playwright (`pip install playwright httpx` в отдельном окружении) и установленный Google Chrome.

1. Создайте отдельную базу и запустите приложение на порту 8010 с `LLM_PROVIDER=fake`, `DICTIONARY_PROVIDER=none`, `COOKIE_SECURE=false`, `ALLOWED_ORIGINS=http://localhost:8010` и `DATABASE_URL`, указывающим на эту базу (`alembic upgrade head`, `python -m app.seed`, `python -m app.verify_seed`).
2. `python scripts/screenshots/seed_demo.py` создает преподавателя, группы, четырех студентов и их ответы (скрипт использует `docker compose exec postgres psql` и базу `vocab_shots`, чтобы сдвинуть даты ответов на день назад).
3. `python scripts/screenshots/take_screenshots.py` сохраняет PNG в `docs/screenshots`.

Все данные вымышленные.
