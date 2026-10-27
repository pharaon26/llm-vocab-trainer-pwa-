from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_today
from app.db import get_db
from app.models import User
from app.config import learning_config
from app.schemas.catalog import DeckOut, DeckSelectionIn
from app.schemas.student import DictionaryEntry, HistoryOut, ProgressOut, SettingsIn, SettingsOut, StatsOut
from app.services import decks as decks_service
from app.services import student as student_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/progress", response_model=ProgressOut)
async def progress(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await student_service.build_progress(db, user)


@router.get("/history", response_model=HistoryOut)
async def history(
    term: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await student_service.build_history(db, user, term, limit, offset)


@router.get("/dictionary", response_model=list[DictionaryEntry])
async def dictionary(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await student_service.build_dictionary(db, user)


@router.get("/stats", response_model=StatsOut)
async def stats(
    days: int = Query(14, ge=7, le=60),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
):
    return await student_service.build_stats(db, user, today, days)


def settings_out(user: User) -> SettingsOut:
    return SettingsOut(
        new_cards_per_day=user.new_cards_per_day,
        min_new_per_day=learning_config.min_new_per_day,
        max_new_per_day=learning_config.max_new_per_day,
    )


@router.get("/settings", response_model=SettingsOut)
async def read_settings(user: User = Depends(current_user)):
    return settings_out(user)


@router.put("/settings", response_model=SettingsOut)
async def update_settings(data: SettingsIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user.new_cards_per_day = data.new_cards_per_day
    await db.commit()
    return settings_out(user)


@router.get("/decks", response_model=list[DeckOut])
async def my_decks(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await decks_service.list_decks(db, user)


@router.put("/decks", response_model=list[DeckOut])
async def choose_decks(data: DeckSelectionIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        await decks_service.select_decks(db, user, data.deck_ids)
    except decks_service.UnknownDecks:
        raise HTTPException(422, "Unknown deck id")
    return await decks_service.list_decks(db, user)
