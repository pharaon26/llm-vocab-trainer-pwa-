from fastapi import FastAPI

from app.api import auth, cards, health, session

app = FastAPI(title="LLM Vocab Trainer")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(session.router)
