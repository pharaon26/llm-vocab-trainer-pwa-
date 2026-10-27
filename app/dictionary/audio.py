from urllib.parse import urlsplit

from app.config import settings


def safe_audio_url(value, domains: list[str] | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    allowed = {domain.lower() for domain in (settings.dictionary_audio_domains if domains is None else domains)}
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        return None
    if (parts.hostname or "").lower() not in allowed:
        return None
    return parts.geturl()
