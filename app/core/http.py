from contextlib import asynccontextmanager
import certifi
import httpx
from app.core.config import get_settings

_shared_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    settings = get_settings()
    verify: bool | str = certifi.where()
    if settings.ca_bundle_path:
        verify = settings.ca_bundle_path
    elif not settings.verify_ssl:
        verify = False

    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        follow_redirects=True,
        verify=verify,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132 Safari/537.36"
            )
        }
    )


async def ensure_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = _build_client()
    return _shared_client


async def close_http_client() -> None:
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


@asynccontextmanager
async def get_http_client():
    yield await ensure_http_client()
