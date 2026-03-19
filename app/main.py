from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, PlainTextResponse

from app.api.routes.tracking import router as tracking_router
from app.core.config import get_settings
from app.core.http import close_http_client, ensure_http_client

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.enable_public_docs else None,
    redoc_url="/redoc" if settings.enable_public_docs else None,
    openapi_url="/openapi.json" if settings.enable_public_docs else None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_size_bytes:
                    return JSONResponse({"detail": "Request body is too large."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length header."}, status_code=400)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


if settings.trusted_hosts_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(
        set(settings.cors_allowed_origins_list or ["http://localhost:5173", "http://127.0.0.1:5173"]).union(
            settings.local_dev_origins if not settings.is_production else set()
        )
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Shared-Secret"],
)


@app.on_event("startup")
async def startup_event() -> None:
    await ensure_http_client()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_http_client()


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")


app.include_router(tracking_router)
