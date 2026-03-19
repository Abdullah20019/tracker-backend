from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter

rate_limiter = SlidingWindowRateLimiter(window_seconds=60)


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}".rstrip("/")

    return None


def client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(request: Request, bucket: str, limit: int) -> None:
    result = rate_limiter.check(f"{bucket}:{client_identifier(request)}", limit)
    if result.allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please slow down and try again shortly.",
        headers={"Retry-After": str(result.retry_after_seconds)},
    )


def verify_public_origin(request: Request) -> None:
    settings = get_settings()
    if not settings.enforce_origin_check:
        return

    allowed_origins = set(settings.public_api_allowed_origins_list)
    if not settings.is_production:
        allowed_origins.update(settings.local_dev_origins)
    if not allowed_origins:
        return

    request_origin = _request_origin(request)
    if not request_origin or request_origin not in allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")


def verify_shared_secret(x_shared_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.backend_shared_secret:
        return
    if x_shared_secret != settings.backend_shared_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid shared secret.")


def verify_public_access(request: Request, x_shared_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.backend_shared_secret and x_shared_secret == settings.backend_shared_secret:
        return
    verify_public_origin(request)
