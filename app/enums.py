from enum import Enum


class ErrorType(str, Enum):
    FORM = "form"
    MEANING = "meaning"
    USAGE = "usage"
    COLLOCATION = "collocation"


class TaskType(str, Enum):
    SPELLING_CHOICE = "spelling_choice"
    DEFINITION_MATCH = "definition_match"
    GAP_FILL = "gap_fill"
    COLLOCATION_CHOICE = "collocation_choice"
    WRITE_TERM = "write_term"


class Role(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
