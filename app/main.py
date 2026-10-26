from fastapi import FastAPI

from app.api import cards, health

app = FastAPI(title="LLM Vocab Trainer")
app.include_router(health.router)
app.include_router(cards.router)
