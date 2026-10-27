from app.config import Settings, draft_config, settings
from app.dictionary.base import DictionaryProvider, DictionaryUnavailable
from app.dictionary.dictionaryapi import DictionaryApiProvider


class DisabledDictionary(DictionaryProvider):
    async def lookup(self, word: str):
        raise DictionaryUnavailable("disabled")


def get_dictionary(config: Settings = settings) -> DictionaryProvider:
    if config.dictionary_provider == "dictionaryapi":
        return DictionaryApiProvider(config.dictionary_url, draft_config.dictionary_timeout)
    return DisabledDictionary()
