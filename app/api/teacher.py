from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_teacher
from app.config import link_config
from app.db import get_db
from app.models import TeacherGroup, TeacherStudent, User
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
from app.services import links

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
