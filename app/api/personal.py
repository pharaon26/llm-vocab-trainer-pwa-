from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_today
from app.config import draft_config
from app.api.session import get_llm_provider
from app.db import get_db
from app.dictionary.base import DictionaryProvider
from app.dictionary.factory import get_dictionary
from app.llm.base import LLMProvider
from app.models import Card, CardDraft, Deck, DeckCard, User
from app.schemas.card import CardCreate
from app.schemas.drafts import (
    CreateDraftOut,
    DraftCreateIn,
    DraftOut,
    DraftUpdateIn,
    DuplicateDeck,
    DuplicateOut,
    ExtractIn,
    ExtractOut,
    LimitsOut,
    PersonalCardOut,
)
from app.services import drafts as drafts_service
from app.services import extract as extract_service
from app.services.visibility import selected_deck_ids

router = APIRouter(prefix="/me", tags=["personal cards"])


@lru_cache
def get_dictionary_provider() -> DictionaryProvider:
    return get_dictionary()


def personal_out(card: Card) -> PersonalCardOut:
    return PersonalCardOut(
        id=card.id, term=card.term, domain=card.domain, transcription=card.transcription,
        part_of_speech=card.part_of_speech, definition_en=card.definition_en,
        translation_ru=card.translation_ru, collocations=card.collocations, examples=card.examples,
        common_mistakes=card.common_mistakes, contrast_term=card.contrast_term, audio_url=card.audio_url,
        sources=dict(card.field_sources or {}),
    )


async def duplicate_out(db: AsyncSession, user: User, card: Card) -> DuplicateOut:
    selected = set(await selected_deck_ids(db, user))
    decks = (
        await db.execute(
            select(Deck.id, Deck.name).join(DeckCard, DeckCard.deck_id == Deck.id).where(DeckCard.card_id == card.id)
        )
    ).all()
    return DuplicateOut(
        id=card.id, term=card.term, domain=card.domain, definition_en=card.definition_en,
        personal=card.owner_id is not None,
        decks=[DuplicateDeck(id=deck_id, name=name, selected=deck_id in selected) for deck_id, name in decks],
    )


async def own_draft(db: AsyncSession, user: User, draft_id: int) -> CardDraft:
    draft = await db.get(CardDraft, draft_id)
    if draft is None or draft.owner_id != user.id:
        raise HTTPException(404, "Draft not found")
    return draft


async def own_card(db: AsyncSession, user: User, card_id: int) -> Card:
    card = await db.get(Card, card_id)
    if card is None or card.owner_id != user.id:
        raise HTTPException(404, "Card not found")
    return card


@router.post("/drafts", response_model=CreateDraftOut)
async def create_draft(
    data: DraftCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
    dictionary: DictionaryProvider = Depends(get_dictionary_provider),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    try:
        draft = await drafts_service.create_draft(db, user, data.term, data.domain, today, dictionary, provider)
    except drafts_service.DuplicateTerm as exc:
        return CreateDraftOut(duplicate=await duplicate_out(db, user, exc.card))
    except drafts_service.UnknownDomain:
        raise HTTPException(422, "Unknown domain")
    except drafts_service.TooManyDrafts:
        raise HTTPException(409, "Too many open drafts: confirm or delete some first")
    return CreateDraftOut(draft=await drafts_service.draft_out(db, draft, user, today))


@router.get("/drafts", response_model=list[DraftOut])
async def list_drafts(user: User = Depends(current_user), db: AsyncSession = Depends(get_db), today: date = Depends(get_today)):
    drafts = (
        await db.scalars(select(CardDraft).where(CardDraft.owner_id == user.id).order_by(CardDraft.id.desc()))
    ).all()
    return [await drafts_service.draft_out(db, draft, user, today) for draft in drafts]


@router.put("/drafts/{draft_id}", response_model=DraftOut)
async def update_draft(
    draft_id: int,
    data: DraftUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
):
    draft = await own_draft(db, user, draft_id)
    try:
        await drafts_service.update_draft(db, draft, data.fields, data.domain)
    except drafts_service.UnknownDomain:
        raise HTTPException(422, "Unknown domain")
    return await drafts_service.draft_out(db, draft, user, today)


@router.post("/drafts/{draft_id}/confirm", response_model=PersonalCardOut, status_code=201)
async def confirm_draft(
    draft_id: int,
    data: DraftUpdateIn | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    draft = await own_draft(db, user, draft_id)
    try:
        if data is not None:
            await drafts_service.update_draft(db, draft, data.fields, data.domain)
        card = await drafts_service.confirm_draft(db, user, draft)
    except drafts_service.UnknownDomain:
        raise HTTPException(422, "Unknown domain")
    except drafts_service.DraftIncomplete as exc:
        raise HTTPException(422, exc.errors)
    except drafts_service.DuplicateTerm:
        raise HTTPException(409, "A card with this term already exists")
    return personal_out(card)


@router.delete("/drafts/{draft_id}", status_code=204)
async def delete_draft(draft_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.delete(await own_draft(db, user, draft_id))
    await db.commit()


@router.get("/cards", response_model=list[PersonalCardOut])
async def my_cards(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    cards = (
        await db.scalars(select(Card).where(Card.owner_id == user.id).order_by(func.lower(Card.term), Card.term))
    ).all()
    return [personal_out(card) for card in cards]


@router.put("/cards/{card_id}", response_model=PersonalCardOut)
async def update_card(card_id: int, data: CardCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    card = await own_card(db, user, card_id)
    clash = await db.scalar(
        select(Card).where(Card.owner_id == user.id, Card.id != card_id, func.lower(Card.term) == data.term.lower())
    )
    if clash:
        raise HTTPException(409, "A card with this term already exists")
    await drafts_service.update_personal_card(db, card, data)
    return personal_out(card)


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(card_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await drafts_service.delete_personal_card(db, await own_card(db, user, card_id))


@router.get("/limits", response_model=LimitsOut)
async def limits(user: User = Depends(current_user), db: AsyncSession = Depends(get_db), today: date = Depends(get_today)):
    return LimitsOut(
        extract_max_chars=draft_config.extract_max_chars,
        extract_max_terms=draft_config.extract_max_terms,
        daily_llm_limit=draft_config.daily_llm_limit,
        llm_calls_left=await drafts_service.llm_calls_left(db, user, today),
    )


@router.post("/extract", response_model=ExtractOut)
async def extract(
    data: ExtractIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    try:
        return await extract_service.extract_terms(db, user, data.text, data.domain, today, provider)
    except extract_service.TextTooLong:
        raise HTTPException(422, f"Text is too long: at most {draft_config.extract_max_chars} characters")
    except drafts_service.UnknownDomain:
        raise HTTPException(422, "Unknown domain")
    except extract_service.LimitReached:
        raise HTTPException(429, "Daily limit of model requests is reached")
    except extract_service.ModelUnavailable:
        raise HTTPException(503, "The model is unavailable, try again later")
