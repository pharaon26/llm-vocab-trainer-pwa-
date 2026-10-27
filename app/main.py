from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, cards, catalog, health, me, my_teachers, personal, practice, session, teacher
from sqlalchemy.exc import DataError

from app.config import BASE_DIR
from app.web_security import security_middleware

app = FastAPI(title="LLM Vocab Trainer")
app.middleware("http")(security_middleware)


@app.exception_handler(DataError)
async def invalid_data(request: Request, exc: DataError):
    return JSONResponse({"detail": "Invalid characters or value in the request"}, status_code=422)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(session.router)
app.include_router(me.router)
app.include_router(practice.router)
app.include_router(catalog.router)
app.include_router(personal.router)
app.include_router(admin.router)
app.include_router(my_teachers.router)
app.include_router(teacher.router)
app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
