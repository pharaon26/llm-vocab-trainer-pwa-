from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_teacher
from app.config import link_config
from app.db import get_db
from app.models import Card, CardProgress, Deck, DeckCard, ReviewHistory, TaskBank, TeacherGroup, TeacherStudent, User
from app.schemas.card import CardCreate, CardRead
from app.schemas.catalog import DeckCardsIn, DeckGroupsIn, DeckIn, TeacherDeckOut
from app.services import decks as decks_service
from app.services.cards import card_values
from app.schemas.links import (
    AcceptIn,
    GroupIn,
    GroupOut,
    InviteIn,
    MoveIn,
    PendingOut,
    SentOut,
    TeacherLinksOut,
)
from app.schemas.teacher import AnalyticsOut
from app.schemas.teacher_students import StudentsOut
from app.services import links
from app.services.analytics import build_analytics
from app.services.teacher_students import build_students, linked_students, teacher_card_scope

router = APIRouter(prefix="/teacher", tags=["teacher"])


def too_many() -> HTTPException:
    return HTTPException(429, "Too many requests, try again later")


async def get_group_or_404(db: AsyncSession, teacher: User, group_id: int) -> TeacherGroup:
    group = await db.scalar(select(TeacherGroup).where(TeacherGroup.id == group_id, TeacherGroup.teacher_id == teacher.id))
    if group is None:
        raise HTTPException(404, "Group not found")
    return group


async def group_out(db: AsyncSession, group: TeacherGroup) -> GroupOut:
    count = await db.scalar(select(func.count()).select_from(TeacherStudent).where(TeacherStudent.group_id == group.id))
    return GroupOut(id=group.id, name=group.name, students=count)


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    groups = await db.scalars(
        select(TeacherGroup).where(TeacherGroup.teacher_id == teacher.id).order_by(func.lower(TeacherGroup.name), TeacherGroup.id)
    )
    return [await group_out(db, group) for group in groups]


@router.post("/groups", response_model=GroupOut, status_code=201)
async def create_group(data: GroupIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(TeacherGroup).where(TeacherGroup.teacher_id == teacher.id))
    if total >= link_config.max_groups:
        raise HTTPException(409, "Too many groups")
    group = TeacherGroup(teacher_id=teacher.id, name=data.name)
    db.add(group)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A group with this name already exists")
    return await group_out(db, group)


@router.put("/groups/{group_id}", response_model=GroupOut)
async def rename_group(group_id: int, data: GroupIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    group = await get_group_or_404(db, teacher, group_id)
    group.name = data.name
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A group with this name already exists")
    return await group_out(db, group)


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(group_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    group = await get_group_or_404(db, teacher, group_id)
    await db.delete(group)
    await db.commit()
    return Response(status_code=204)


@router.get("/links", response_model=TeacherLinksOut)
async def pending_links(teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    requests, invitations = await links.pending_for_teacher(db, teacher)
    return TeacherLinksOut(
        requests=[PendingOut(id=i, name=n) for i, n in requests],
        invitations=[PendingOut(id=i, name=n) for i, n in invitations],
    )


@router.post("/invitations", response_model=SentOut, status_code=202)
async def invite_student(data: InviteIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        await links.invite(db, teacher, data.name, data.group_id)
    except links.NotFound:
        raise HTTPException(404, "Group not found")
    except links.TooManyRequests:
        raise too_many()
    return SentOut()


@router.delete("/invitations/{request_id}", status_code=204)
async def cancel_invitation(request_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        await links.cancel_own(db, teacher, request_id, links.INVITE)
    except links.NotFound:
        raise HTTPException(404, "Invitation not found")
    return Response(status_code=204)


@router.post("/requests/{request_id}/accept", status_code=204)
async def accept_request(request_id: int, data: AcceptIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        await links.teacher_answers_request(db, teacher, request_id, True, data.group_id)
    except links.NotFound:
        raise HTTPException(404, "Request or group not found")
    return Response(status_code=204)


@router.post("/requests/{request_id}/decline", status_code=204)
async def decline_request(request_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        await links.teacher_answers_request(db, teacher, request_id, False, None)
    except links.NotFound:
        raise HTTPException(404, "Request not found")
    return Response(status_code=204)


@router.delete("/students/{nickname}", status_code=204)
async def remove_student(nickname: str, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        student = await links.linked_student(db, teacher, nickname)
        await links.break_link(db, teacher_id=teacher.id, student_id=student.id)
    except links.NotFound:
        raise HTTPException(404, "Student not found")
    return Response(status_code=204)


@router.put("/students/{nickname}/group", status_code=204)
async def move_student(nickname: str, data: MoveIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    try:
        await links.move_student(db, teacher, nickname, data.group_id)
    except links.NotFound:
        raise HTTPException(404, "Student or group not found")
    return Response(status_code=204)


@router.get("/students", response_model=StudentsOut)
async def students(teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    return await build_students(db, teacher)


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(
    group_id: int | None = None,
    min_answers: int = Query(3, ge=1),
    limit: int = Query(10, ge=1, le=50),
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    if group_id is not None:
        await get_group_or_404(db, teacher, group_id)
    return await build_analytics(
        db, min_answers, limit, users=linked_students(teacher, group_id), cards=teacher_card_scope(teacher)
    )


async def own_card(db: AsyncSession, teacher: User, card_id: int) -> Card:
    card = await db.scalar(select(Card).where(Card.id == card_id, Card.owner_id == teacher.id))
    if card is None:
        raise HTTPException(404, "Card not found")
    return card


async def ensure_own_term_free(db: AsyncSession, teacher: User, term: str, exclude_id: int | None = None) -> None:
    existing = await db.scalar(select(Card).where(func.lower(Card.term) == term.lower(), Card.owner_id == teacher.id))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "You already have a card with this term")


@router.get("/cards", response_model=list[CardRead])
async def list_cards(teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    query = select(Card).where(Card.owner_id == teacher.id).order_by(func.lower(Card.term), Card.term)
    return (await db.scalars(query)).all()


@router.post("/cards", response_model=CardRead, status_code=201)
async def create_card(data: CardCreate, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await ensure_own_term_free(db, teacher, data.term)
    card = Card(**await card_values(db, data.model_dump()), verified=True, owner_id=teacher.id, confirmed_by_owner=True)
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.get("/cards/{card_id}", response_model=CardRead)
async def read_card(card_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    return await own_card(db, teacher, card_id)


@router.put("/cards/{card_id}", response_model=CardRead)
async def update_card(card_id: int, data: CardCreate, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    card = await own_card(db, teacher, card_id)
    await ensure_own_term_free(db, teacher, data.term, exclude_id=card_id)
    for field, value in (await card_values(db, data.model_dump())).items():
        setattr(card, field, value)
    await db.commit()
    await db.refresh(card)
    return card


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(card_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    card = await own_card(db, teacher, card_id)
    for model in (ReviewHistory, CardProgress, TaskBank, DeckCard):
        await db.execute(delete(model).where(model.card_id == card_id))
    await db.delete(card)
    await db.commit()
    return Response(status_code=204)


async def own_deck(db: AsyncSession, teacher: User, deck_id: int) -> Deck:
    deck = await db.scalar(select(Deck).where(Deck.id == deck_id, Deck.owner_id == teacher.id))
    if deck is None:
        raise HTTPException(404, "Deck not found")
    return deck


async def ensure_own_deck_name_free(db: AsyncSession, teacher: User, name: str, exclude_id: int | None = None) -> None:
    existing = await db.scalar(select(Deck).where(func.lower(Deck.name) == name.lower(), Deck.owner_id == teacher.id))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "You already have a deck with this name")


@router.get("/decks", response_model=list[TeacherDeckOut])
async def list_decks(teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    decks = await db.scalars(select(Deck).where(Deck.owner_id == teacher.id).order_by(func.lower(Deck.name), Deck.name))
    return [await decks_service.teacher_deck(db, deck) for deck in decks]


@router.post("/decks", response_model=TeacherDeckOut, status_code=201)
async def create_deck(data: DeckIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await ensure_own_deck_name_free(db, teacher, data.name)
    deck = Deck(owner_id=teacher.id)
    await decks_service.apply_deck(db, deck, data.name, data.description, data.domain, False)
    db.add(deck)
    await db.commit()
    return await decks_service.teacher_deck(db, deck)


@router.put("/decks/{deck_id}", response_model=TeacherDeckOut)
async def update_deck(deck_id: int, data: DeckIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    deck = await own_deck(db, teacher, deck_id)
    await ensure_own_deck_name_free(db, teacher, data.name, exclude_id=deck_id)
    await decks_service.apply_deck(db, deck, data.name, data.description, data.domain, False)
    await db.commit()
    return await decks_service.teacher_deck(db, deck)


@router.put("/decks/{deck_id}/cards", response_model=TeacherDeckOut)
async def set_deck_cards(deck_id: int, data: DeckCardsIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    deck = await own_deck(db, teacher, deck_id)
    try:
        await decks_service.set_deck_cards(db, deck, data.card_ids)
    except decks_service.UnknownDecks:
        raise HTTPException(422, "Unknown card id")
    return await decks_service.teacher_deck(db, deck)


@router.put("/decks/{deck_id}/groups", response_model=TeacherDeckOut)
async def set_deck_groups(deck_id: int, data: DeckGroupsIn, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    deck = await own_deck(db, teacher, deck_id)
    try:
        await decks_service.set_deck_groups(db, deck, data.group_ids)
    except decks_service.UnknownGroups:
        raise HTTPException(422, "Unknown group id")
    return await decks_service.teacher_deck(db, deck)


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(deck_id: int, teacher: User = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await decks_service.delete_deck(db, await own_deck(db, teacher, deck_id))
    return Response(status_code=204)
