from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class DictionaryUnavailable(Exception):
    pass


@dataclass
class DictionaryEntry:
    transcription: str | None = None
    part_of_speech: str | None = None
    definition: str | None = None
    examples: list[str] = field(default_factory=list)
    audio_url: str | None = None


class DictionaryProvider(ABC):
    @abstractmethod
    def lookup(self, word: str) -> DictionaryEntry | None:
        """Возвращает запись или None, если слова нет. Если сервис недоступен, бросает DictionaryUnavailable."""
