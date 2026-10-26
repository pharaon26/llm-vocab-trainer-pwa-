# LLM Vocab Trainer

PWA для усвоения профессиональной англоязычной лексики (ИТ и информационная безопасность) с интервальным повторением и генерацией заданий языковой моделью.

## Запуск

Нужен Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # затем заполните значения
alembic upgrade head        # применить миграции
uvicorn app.main:app --reload
```

- Проверка: http://localhost:8000/health возвращает `{"status": "ok"}`
- Документация API: http://localhost:8000/docs

## Тесты

```bash
pytest
```

## Структура

- `app/main.py` - точка входа FastAPI
- `app/config.py` - настройки из `.env`
- `app/db.py` - подключение к БД и сессии
- `app/api/` - маршруты, `app/models/` - таблицы, `app/schemas/` - Pydantic-схемы
- `alembic/` - миграции
- `tests/` - тесты pytest
- `static/` - фронтенд PWA (позже)

## Секреты

Ключи хранятся только в `.env` (он в `.gitignore`). Шаблон - `.env.example`.
