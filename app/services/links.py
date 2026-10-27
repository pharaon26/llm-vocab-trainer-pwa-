from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LinkConfig, link_config
from app.enums import Role
from app.models import LinkAttempt, LinkRequest, TeacherGroup, TeacherStudent, User

PENDING, ACCEPTED, DECLINED, CANCELLED = "pending", "accepted", "declined", "cancelled"
INVITE, REQUEST = "invite", "request"


class TooManyRequests(Exception):
    pass


class NotFound(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


async def register_attempt(db: AsyncSession, sender: User, config: LinkConfig = link_config, now: datetime | None = None) -> None:
    now = now or _now()
    recent = await db.scalar(
        select(func.count()).select_from(LinkAttempt).where(
            LinkAttempt.sender_id == sender.id, LinkAttempt.created_at > now - timedelta(minutes=config.window_minutes)
        )
    )
    if recent >= config.max_attempts:
        raise TooManyRequests
    db.add(LinkAttempt(sender_id=sender.id, created_at=now))
    await db.execute(delete(LinkAttempt).where(LinkAttempt.created_at < now - timedelta(days=1)))
    await db.commit()


async def user_by_nickname(db: AsyncSession, nickname: str, role: Role) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.name) == nickname.lower(), User.role == role.value))


async def is_linked(db: AsyncSession, teacher_id: int, student_id: int) -> bool:
    return await db.get(TeacherStudent, (teacher_id, student_id)) is not None


async def own_group(db: AsyncSession, teacher: User, group_id: int | None) -> TeacherGroup | None:
    if group_id is None:
        return None
    group = await db.scalar(select(TeacherGroup).where(TeacherGroup.id == group_id, TeacherGroup.teacher_id == teacher.id))
    if group is None:
        raise NotFound
    return group


async def _pending(db: AsyncSession, teacher_id: int, student_id: int) -> LinkRequest | None:
    return await db.scalar(
        select(LinkRequest).where(
            LinkRequest.teacher_id == teacher_id, LinkRequest.student_id == student_id, LinkRequest.status == PENDING
        )
    )


async def _link(db: AsyncSession, request: LinkRequest | None, teacher_id: int, student_id: int, group_id: int | None) -> None:
    if request is not None:
        request.status = ACCEPTED
    if not await is_linked(db, teacher_id, student_id):
        db.add(TeacherStudent(teacher_id=teacher_id, student_id=student_id, group_id=group_id))


async def invite(db: AsyncSession, teacher: User, nickname: str, group_id: int | None) -> None:
    group = await own_group(db, teacher, group_id)
    await register_attempt(db, teacher)
    student = await user_by_nickname(db, nickname, Role.STUDENT)
    if student is None or await is_linked(db, teacher.id, student.id):
        return
    pending = await _pending(db, teacher.id, student.id)
    if pending is None:
        db.add(LinkRequest(teacher_id=teacher.id, student_id=student.id, direction=INVITE, group_id=group_id, status=PENDING))
    elif pending.direction == REQUEST:
        await _link(db, pending, teacher.id, student.id, group.id if group else None)
    await db.commit()


async def request_teacher(db: AsyncSession, student: User, nickname: str) -> None:
    await register_attempt(db, student)
    teacher = await user_by_nickname(db, nickname, Role.TEACHER)
    if teacher is None or await is_linked(db, teacher.id, student.id):
        return
    pending = await _pending(db, teacher.id, student.id)
    if pending is None:
        db.add(LinkRequest(teacher_id=teacher.id, student_id=student.id, direction=REQUEST, status=PENDING))
    elif pending.direction == INVITE:
        await _link(db, pending, teacher.id, student.id, pending.group_id)
    await db.commit()


async def _own_pending(db: AsyncSession, request_id: int, direction: str, **owner) -> LinkRequest:
    request = await db.scalar(
        select(LinkRequest).where(
            LinkRequest.id == request_id, LinkRequest.direction == direction, LinkRequest.status == PENDING,
            *[getattr(LinkRequest, key) == value for key, value in owner.items()],
        )
    )
    if request is None:
        raise NotFound
    return request


async def student_answers_invitation(db: AsyncSession, student: User, request_id: int, accept: bool) -> None:
    request = await _own_pending(db, request_id, INVITE, student_id=student.id)
    if accept:
        await _link(db, request, request.teacher_id, student.id, request.group_id)
    else:
        request.status = DECLINED
    await db.commit()


async def teacher_answers_request(db: AsyncSession, teacher: User, request_id: int, accept: bool, group_id: int | None) -> None:
    request = await _own_pending(db, request_id, REQUEST, teacher_id=teacher.id)
    if accept:
        group = await own_group(db, teacher, group_id)
        await _link(db, request, teacher.id, request.student_id, group.id if group else None)
    else:
        request.status = DECLINED
    await db.commit()


async def cancel_own(db: AsyncSession, user: User, request_id: int, direction: str) -> None:
    owner = {"teacher_id": user.id} if direction == INVITE else {"student_id": user.id}
    request = await _own_pending(db, request_id, direction, **owner)
    request.status = CANCELLED
    await db.commit()


async def break_link(db: AsyncSession, *, teacher_id: int, student_id: int) -> None:
    result = await db.execute(
        delete(TeacherStudent).where(TeacherStudent.teacher_id == teacher_id, TeacherStudent.student_id == student_id)
    )
    if result.rowcount == 0:
        raise NotFound
    await db.commit()


async def linked_student(db: AsyncSession, teacher: User, nickname: str) -> User:
    student = await db.scalar(
        select(User)
        .join(TeacherStudent, TeacherStudent.student_id == User.id)
        .where(TeacherStudent.teacher_id == teacher.id, func.lower(User.name) == nickname.lower())
    )
    if student is None:
        raise NotFound
    return student


async def move_student(db: AsyncSession, teacher: User, nickname: str, group_id: int | None) -> None:
    group = await own_group(db, teacher, group_id)
    student = await linked_student(db, teacher, nickname)
    await db.execute(
        update(TeacherStudent)
        .where(TeacherStudent.teacher_id == teacher.id, TeacherStudent.student_id == student.id)
        .values(group_id=group.id if group else None)
    )
    await db.commit()


async def pending_for_teacher(db: AsyncSession, teacher: User) -> tuple[list, list]:
    rows = (
        await db.execute(
            select(LinkRequest.id, LinkRequest.direction, User.name)
            .join(User, User.id == LinkRequest.student_id)
            .where(LinkRequest.teacher_id == teacher.id, LinkRequest.status == PENDING)
            .order_by(LinkRequest.id)
        )
    ).all()
    return [(i, n) for i, d, n in rows if d == REQUEST], [(i, n) for i, d, n in rows if d == INVITE]


async def teachers_of(db: AsyncSession, student: User) -> tuple[list[str], list, list]:
    teachers = list(
        await db.scalars(
            select(User.name).join(TeacherStudent, TeacherStudent.teacher_id == User.id)
            .where(TeacherStudent.student_id == student.id).order_by(func.lower(User.name))
        )
    )
    rows = (
        await db.execute(
            select(LinkRequest.id, LinkRequest.direction, User.name)
            .join(User, User.id == LinkRequest.teacher_id)
            .where(LinkRequest.student_id == student.id, LinkRequest.status == PENDING)
            .order_by(LinkRequest.id)
        )
    ).all()
    return teachers, [(i, n) for i, d, n in rows if d == INVITE], [(i, n) for i, d, n in rows if d == REQUEST]
