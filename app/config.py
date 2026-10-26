from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import ErrorType


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    gigachat_api_key: str = ""


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
    error_rules: dict[ErrorType, ErrorRule] = field(
        default_factory=lambda: {
            ErrorType.FORM: ErrorRule(k=0.5, delta=0.10),
            ErrorType.MEANING: ErrorRule(k=0.0, delta=0.20),
            ErrorType.USAGE: ErrorRule(k=0.5, delta=0.15),
            ErrorType.COLLOCATION: ErrorRule(k=0.6, delta=0.10),
        }
    )


scheduler_config = SchedulerConfig()
