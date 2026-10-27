from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.enums import ErrorType

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20
    llm_provider: Literal["fake", "gigachat"] = "fake"
    llm_temperature: float = 0.3
    llm_timeout: float = 30.0
    student_level: str = "B1"
    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    gigachat_ca_bundle: str = "certs/russian_trusted_root_ca_pem.crt"
    dictionary_provider: Literal["dictionaryapi", "none"] = "dictionaryapi"
    dictionary_url: str = "https://api.dictionaryapi.dev/api/v2/entries/en"
    teacher_password: str = ""
    session_ttl_days: int = 30
    session_cookie_name: str = "session"
    cookie_secure: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    trusted_proxies: Annotated[list[str], NoDecode] = []
    dictionary_audio_domains: Annotated[list[str], NoDecode] = ["api.dictionaryapi.dev", "ssl.gstatic.com"]

    @field_validator("trusted_proxies", "dictionary_audio_domains", "allowed_origins", mode="before")
    @classmethod
    def split_list(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()


@dataclass(frozen=True)
class AuthConfig:
    password_min_length: int = 8
    password_max_length: int = 128
    login_max_failures: int = 5
    login_window_minutes: int = 15


auth_config = AuthConfig()


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


@dataclass(frozen=True)
class GenerationConfig:
    max_retries: int = 2
    bank_min_size: int = 3
    options_count: int = 4


generation_config = GenerationConfig()


@dataclass(frozen=True)
class ClassificationConfig:
    max_retries: int = 2
    typo_distance: int = 2
    situations: tuple[str, ...] = (
        "Вы пишете отчет об инциденте информационной безопасности для руководителя.",
        "Вы объясняете коллеге из другой команды, почему релиз пришлось отложить.",
        "Вы пишете комментарий к pull request.",
        "Вы описываете проблему в тикете для службы поддержки.",
        "Вы готовите для заказчика отчет по результатам тестирования системы.",
        "Вы объясняете новому сотруднику, как устроена защита вашего сервиса.",
    )


classification_config = ClassificationConfig()


@dataclass(frozen=True)
class LearningConfig:
    learned_interval_days: float = 21
    min_new_per_day: int = 1
    max_new_per_day: int = 20


learning_config = LearningConfig()


@dataclass(frozen=True)
class DraftConfig:
    daily_llm_limit: int = 30
    max_retries: int = 2
    dictionary_timeout: float = 3.0
    extract_max_chars: int = 4000
    extract_max_terms: int = 15
    max_open_drafts: int = 50


draft_config = DraftConfig()
