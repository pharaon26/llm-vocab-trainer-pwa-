from app.dictionary.base import DictionaryEntry, DictionaryProvider, DictionaryUnavailable


class FakeDictionary(DictionaryProvider):
    def __init__(self, entries: dict[str, DictionaryEntry] | None = None, unavailable: bool = False):
        self.entries = {key.lower(): value for key, value in (entries or {}).items()}
        self.unavailable = unavailable
        self.calls: list[str] = []

    def lookup(self, word: str) -> DictionaryEntry | None:
        self.calls.append(word)
        if self.unavailable:
            raise DictionaryUnavailable("fake outage")
        return self.entries.get(word.lower())
