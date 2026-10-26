from enum import Enum


class ErrorType(str, Enum):
    FORM = "form"
    MEANING = "meaning"
    USAGE = "usage"
    COLLOCATION = "collocation"

