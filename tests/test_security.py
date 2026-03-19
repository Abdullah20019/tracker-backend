from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest

from app.api.deps import enforce_rate_limit, rate_limiter, verify_public_origin, verify_shared_secret


def test_public_origin_allows_configured_origin(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_ALLOWED_ORIGINS", "https://www.paktrack.pk")
    monkeypatch.setenv("ENFORCE_ORIGIN_CHECK", "true")

    from app.core.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()

    @app.post("/track")
    def track(request: Request):
        verify_public_origin(request)
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/track", headers={"Origin": "https://www.paktrack.pk"})
    assert response.status_code == 200


def test_public_origin_blocks_unknown_origin(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_ALLOWED_ORIGINS", "https://www.paktrack.pk")
    monkeypatch.setenv("ENFORCE_ORIGIN_CHECK", "true")

    from app.core.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()

    @app.post("/track")
    def track(request: Request):
        verify_public_origin(request)
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/track", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_rate_limit_blocks_after_threshold():
    rate_limiter._hits.clear()
    app = FastAPI()

    @app.get("/health")
    def health(request: Request):
        enforce_rate_limit(request, "health-test", 2)
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    response = client.get("/health")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_shared_secret_blocks_invalid_value(monkeypatch):
    monkeypatch.setenv("BACKEND_SHARED_SECRET", "super-secret")

    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(HTTPException) as error:
        verify_shared_secret(None)
    assert error.value.status_code == 401
