from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def origin_of(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def request_origin_allowed(origin: str | None, referer: str | None, allowed: list[str]) -> bool:
    allowed_origins = {origin_of(item) for item in allowed} - {None}
    if origin is not None:
        return origin_of(origin) in allowed_origins
    return origin_of(referer) in allowed_origins


def content_security_policy() -> str:
    media = " ".join(["'self'", *(f"https://{domain}" for domain in settings.dictionary_audio_domains)])
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            f"media-src {media}",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


async def security_middleware(request: Request, call_next):
    if request.method in UNSAFE_METHODS and not request_origin_allowed(
        request.headers.get("origin"), request.headers.get("referer"), settings.allowed_origins
    ):
        response = JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
    else:
        response = await call_next(request)
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers["Content-Security-Policy"] = content_security_policy()
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
