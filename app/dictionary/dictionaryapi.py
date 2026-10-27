import re
from urllib.parse import quote

import httpx

from app.dictionary.base import DictionaryEntry, DictionaryProvider, DictionaryUnavailable

MAX_EXAMPLES = 3


def contains_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}", text, re.IGNORECASE) is not None


def _transcription(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().strip("/").strip()
    return f"/{value}/" if value else None


def _audio(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("//"):
        value = f"https:{value}"
    return value if value.startswith("https://") else None


def parse_entries(payload, word: str) -> DictionaryEntry | None:
    if not isinstance(payload, list) or not payload:
        return None
    entry = DictionaryEntry()
    for item in payload:
        if not isinstance(item, dict):
            continue
        entry.transcription = entry.transcription or _transcription(item.get("phonetic"))
        for phonetic in item.get("phonetics") or []:
            if isinstance(phonetic, dict):
                entry.transcription = entry.transcription or _transcription(phonetic.get("text"))
                entry.audio_url = entry.audio_url or _audio(phonetic.get("audio"))
        for meaning in item.get("meanings") or []:
            if not isinstance(meaning, dict):
                continue
            definitions = [d for d in meaning.get("definitions") or [] if isinstance(d, dict)]
            if entry.definition is None and definitions and isinstance(definitions[0].get("definition"), str):
                entry.part_of_speech = meaning.get("partOfSpeech") or None
                entry.definition = definitions[0]["definition"].strip() or None
            for definition in definitions:
                example = definition.get("example")
                if (
                    isinstance(example, str)
                    and contains_word(example, word)
                    and example.strip() not in entry.examples
                    and len(entry.examples) < MAX_EXAMPLES
                ):
                    entry.examples.append(example.strip())
    if not (entry.definition or entry.transcription or entry.examples):
        return None
    return entry


class DictionaryApiProvider(DictionaryProvider):
    def __init__(self, base_url: str, timeout: float, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = client

    async def lookup(self, word: str) -> DictionaryEntry | None:
        url = f"{self.base_url}/{quote(word, safe='')}"
        try:
            if self.client is not None:
                response = await self.client.get(url, timeout=self.timeout, follow_redirects=True)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=self.timeout, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise DictionaryUnavailable(type(exc).__name__) from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DictionaryUnavailable(f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DictionaryUnavailable("invalid JSON") from exc
        return parse_entries(payload, word)
