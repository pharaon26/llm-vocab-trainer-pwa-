from abc import ABC, abstractmethod


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Возвращает текст ответа модели на пару system и user."""
