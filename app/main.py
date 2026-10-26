from fastapi import FastAPI

from app.api import health

app = FastAPI(title="LLM Vocab Trainer")
app.include_router(health.router)
