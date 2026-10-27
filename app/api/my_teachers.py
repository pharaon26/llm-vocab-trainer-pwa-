from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.db import get_db
from app.models import User
from app.schemas.links import MyTeachersOut, PendingOut, PersonOut, SendIn, SentOut
from app.services import links

router = APIRouter(prefix="/me", tags=["my teachers"])


def too_many() -> HTTPException:
    return HTTPException(429, "Too many requests, try again later")


@router.get("/teachers", response_model=MyTeachersOut)
async def my_teachers(user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    teachers, invitations, requests = await links.teachers_of(db, user)
    return MyTeachersOut(
        teachers=[PersonOut(name=name) for name in teachers],
        invitations=[PendingOut(id=i, name=n) for i, n in invitations],
        requests=[PendingOut(id=i, name=n) for i, n in requests],
    )


@router.post("/teachers/requests", response_model=SentOut, status_code=202)
async def request_teacher(data: SendIn, user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    try:
        await links.request_teacher(db, user, data.name)
    except links.TooManyRequests:
        raise too_many()
    return SentOut()


@router.post("/invitations/{request_id}/accept", status_code=204)
async def accept_invitation(request_id: int, user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    try:
        await links.student_answers_invitation(db, user, request_id, accept=True)
    except links.NotFound:
        raise HTTPException(404, "Invitation not found")
    return Response(status_code=204)


@router.post("/invitations/{request_id}/decline", status_code=204)
async def decline_invitation(request_id: int, user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    try:
        await links.student_answers_invitation(db, user, request_id, accept=False)
    except links.NotFound:
        raise HTTPException(404, "Invitation not found")
    return Response(status_code=204)


@router.delete("/requests/{request_id}", status_code=204)
async def cancel_request(request_id: int, user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    try:
        await links.cancel_own(db, user, request_id, links.REQUEST)
    except links.NotFound:
        raise HTTPException(404, "Request not found")
    return Response(status_code=204)


@router.delete("/teachers/{nickname}", status_code=204)
async def leave_teacher(nickname: str, user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    teacher = await db.scalar(select(User).where(func.lower(User.name) == nickname.lower()))
    if teacher is None:
        raise HTTPException(404, "Teacher not found")
    try:
        await links.break_link(db, teacher_id=teacher.id, student_id=user.id)
    except links.NotFound:
        raise HTTPException(404, "Teacher not found")
    return Response(status_code=204)
