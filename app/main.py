from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth, cards, catalog, health, me, personal, practice, session, teacher
from app.config import BASE_DIR

app = FastAPI(title="LLM Vocab Trainer")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(session.router)
app.include_router(me.router)
app.include_router(practice.router)
app.include_router(catalog.router)
app.include_router(personal.router)
app.include_router(teacher.router)
app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
