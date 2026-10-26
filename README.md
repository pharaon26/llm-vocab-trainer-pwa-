# LLM Vocab Trainer

PWA для усвоения профессиональной англоязычной лексики (ИТ и информационная безопасность) с интервальным повторением и генерацией заданий языковой моделью.

## Запуск

Нужен Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # затем заполните значения (TEACHER_PASSWORD)
alembic upgrade head        # применить миграции
python -m app.seed          # загрузить стартовые карточки
python -m app.verify_seed   # пометить карточки сида проверенными (см. ниже)
uvicorn app.main:app --reload
```

- Проверка: http://localhost:8000/health возвращает `{"status": "ok"}`
- Документация API: http://localhost:8000/docs

## Проверка карточек

Загрузка сида (`app.seed`) создает карточки с `verified=false`, и в сессию студента они не попадают. Перед командой `python -m app.verify_seed` содержимое `data/cards.json` нужно просмотреть глазами (транскрипции, определения, примеры, типичные ошибки): команда помечает проверенными все карточки сида сразу.

## Вход (упрощение прототипа)

- Студент входит по имени без пароля: `POST /auth/login` с `{"name": "..."}`. Тот же ввод имени дает тот же аккаунт, поэтому чужим именем можно воспользоваться.
- Преподаватель входит с `"role": "teacher"` и общим паролем из `TEACHER_PASSWORD` в `.env`. Если пароль не задан, вход преподавателя отключен.
- Ответ содержит случайный токен, который хранится в БД и передается в заголовке `Authorization: Bearer <token>`. Срока действия у токенов и выхода из системы пока нет.
- Создание, правка, удаление и проверка карточек доступны только преподавателю.

## Генерация заданий через LLM

Провайдер выбирается в `.env`: `LLM_PROVIDER=fake` (по умолчанию, без ключа и сети) или `LLM_PROVIDER=gigachat`.

Для GigaChat нужны:
- `GIGACHAT_CREDENTIALS` - «Ключ авторизации» из личного кабинета;
- `GIGACHAT_SCOPE=GIGACHAT_API_PERS` (тариф для физических лиц);
- модель по умолчанию `GigaChat-2`, задается `GIGACHAT_MODEL`.

Адреса API берутся из официального SDK `gigachat` (версия 0.2.3: `https://api.giga.chat/v1`, авторизация `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`). Подключение проверялось только до уровня создания клиента, реальный запрос с ключом еще не выполнялся.

Проверка TLS включена всегда. Для нее используется корневой сертификат НУЦ Минцифры `certs/russian_trusted_root_ca_pem.crt`. Он публичный, скачан с https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt (Russian Trusted Root CA, действует до 27.02.2032, SHA-256: `D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31`). Отключать проверку сертификата нельзя.

В модель уходят только поля карточки, тип задания и уровень студента. Имена и ответы студентов в запрос не попадают.

Проверка генерации вручную:

```bash
python -m app.generate vulnerability gap_fill
```

Типы заданий: `gap_fill`, `collocation_choice`, `definition_match`.

## Тесты

```bash
pytest
```

## Структура

- `app/main.py` - точка входа FastAPI
- `app/config.py` - настройки из `.env`
- `app/db.py` - подключение к БД и сессии
- `app/api/` - маршруты, `app/models/` - таблицы, `app/schemas/` - Pydantic-схемы
- `app/seed.py`, `data/cards.json` - загрузка стартовых карточек
- `app/llm/` - адаптеры LLM (`fake`, `gigachat`), шаблон запроса
- `app/services/generation.py` - сборка запроса и разбор ответа модели
- `certs/` - корневой сертификат для GigaChat
- `alembic/` - миграции
- `tests/` - тесты pytest
- `static/` - фронтенд PWA (позже)

## Секреты

Ключи хранятся только в `.env` (он в `.gitignore`). Шаблон - `.env.example`.
