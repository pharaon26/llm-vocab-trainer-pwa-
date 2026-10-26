from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import ErrorType

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    llm_provider: Literal["fake", "gigachat"] = "fake"
    llm_temperature: float = 0.3
    llm_timeout: float = 30.0
    student_level: str = "B1"
    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    gigachat_ca_bundle: str = "certs/russian_trusted_root_ca_pem.crt"
    teacher_password: str = ""


settings = Settings()


@dataclass(frozen=True)
class ErrorRule:
    k: float
    delta: float


@dataclass(frozen=True)
class SchedulerConfig:
    ease_start: float = 2.5
    ease_min: float = 1.3
    ease_max: float = 2.5
    ease_step: float = 0.05
    first_interval: float = 1
    second_interval: float = 3
    new_cards_per_day: int = 5
    error_rules: dict[ErrorType, ErrorRule] = field(
        default_factory=lambda: {
            ErrorType.FORM: ErrorRule(k=0.5, delta=0.10),
            ErrorType.MEANING: ErrorRule(k=0.0, delta=0.20),
            ErrorType.USAGE: ErrorRule(k=0.5, delta=0.15),
            ErrorType.COLLOCATION: ErrorRule(k=0.6, delta=0.10),
        }
    )


scheduler_config = SchedulerConfig()
