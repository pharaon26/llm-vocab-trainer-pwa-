from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LearningConfig, learning_config
from app.models import Card, CardProgress, ReviewHistory, TeacherGroup, TeacherStudent, User
from app.schemas.teacher_students import StudentGroup, StudentsOut, StudentSummary


def teacher_card_scope(teacher: User):
    return or_(Card.owner_id.is_(None), Card.owner_id == teacher.id)


def linked_students(teacher: User, group_id: int | None = None):
    query = select(TeacherStudent.student_id).where(TeacherStudent.teacher_id == teacher.id)
    if group_id is not None:
        query = query.where(TeacherStudent.group_id == group_id)
    return User.id.in_(query)


async def build_students(db: AsyncSession, teacher: User, config: LearningConfig = learning_config) -> StudentsOut:
    scope = teacher_card_scope(teacher)
    links = (
        await db.execute(
            select(TeacherStudent.group_id, User.id, User.name)
            .join(User, User.id == TeacherStudent.student_id)
            .where(TeacherStudent.teacher_id == teacher.id)
            .order_by(func.lower(User.name))
        )
    ).all()
    ids = [student_id for _, student_id, _ in links]

    learned = dict(
        (
            await db.execute(
                select(CardProgress.user_id, func.count())
                .join(Card, Card.id == CardProgress.card_id)
                .where(
                    CardProgress.user_id.in_(ids), scope, CardProgress.pending_interval.is_(None),
                    CardProgress.interval >= config.learned_interval_days,
                )
                .group_by(CardProgress.user_id)
            )
        ).all()
    )
    correct = case((ReviewHistory.is_correct.is_(True), 1), else_=0)
    answers = {
        user_id: (total, right, last)
        for user_id, total, right, last in (
            await db.execute(
                select(ReviewHistory.user_id, func.count(), func.sum(correct), func.max(ReviewHistory.answered_on))
                .join(Card, Card.id == ReviewHistory.card_id)
                .where(ReviewHistory.user_id.in_(ids), scope, ReviewHistory.is_practice.is_(False))
                .group_by(ReviewHistory.user_id)
            )
        ).all()
    }
    first_attempts = {
        user_id: (total, right)
        for user_id, total, right in (
            await db.execute(
                select(ReviewHistory.user_id, func.count(), func.sum(correct))
                .join(Card, Card.id == ReviewHistory.card_id)
                .where(
                    ReviewHistory.user_id.in_(ids), scope, ReviewHistory.is_practice.is_(False),
                    ReviewHistory.is_retry.is_(False),
                )
                .group_by(ReviewHistory.user_id)
            )
        ).all()
    }

    def summary(student_id: int, name: str) -> StudentSummary:
        total, right = first_attempts.get(student_id, (0, 0))
        last = answers.get(student_id, (0, 0, None))[2]
        return StudentSummary(
            name=name, learned=learned.get(student_id, 0), answered=total,
            accuracy=round(right / total, 3) if total else None, last_active=last,
        )

    groups = (
        await db.execute(
            select(TeacherGroup.id, TeacherGroup.name)
            .where(TeacherGroup.teacher_id == teacher.id)
            .order_by(func.lower(TeacherGroup.name), TeacherGroup.id)
        )
    ).all()
    result = [
        StudentGroup(id=gid, name=name, students=[summary(sid, n) for g, sid, n in links if g == gid])
        for gid, name in groups
    ]
    ungrouped = [summary(sid, n) for g, sid, n in links if g is None]
    if ungrouped:
        result.append(StudentGroup(id=None, name=None, students=ungrouped))
    return StudentsOut(groups=result)
