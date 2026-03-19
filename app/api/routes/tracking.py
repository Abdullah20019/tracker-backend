from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.registry import registry
from app.api.deps import enforce_rate_limit, verify_public_access, verify_shared_secret
from app.core.cache import TTLCache
from app.core.config import get_settings
from app.core.errors import CourierNotSupportedError, InvalidTrackingNumberError, TrackingError
from app.core.schemas import (
    BulkTrackRequest,
    CourierDescriptor,
    InternalCourierStatus,
    TrackRequest,
    TrackingResult,
)

router = APIRouter()
settings = get_settings()
cache = TTLCache[TrackingResult](settings.cache_ttl_seconds)
logger = logging.getLogger(__name__)


def build_cache_key(courier: str, tracking_number: str) -> str:
    return f"{courier.lower()}::{tracking_number.strip().upper()}"


async def resolve_result(courier: str | None, tracking_number: str, auto_detect: bool) -> TrackingResult:
    adapter = registry.detect(tracking_number) if auto_detect or not courier else registry.resolve(courier)
    cache_key = build_cache_key(adapter.id, tracking_number)
    cached = cache.get(cache_key)
    if cached:
        return cached.model_copy(update={"cached": True})

    result = await adapter.timed_track(tracking_number)
    normalized = adapter.normalize(result)
    cache.set(cache_key, normalized)
    return normalized


@router.get("/health")
async def health_check(request: Request):
    enforce_rate_limit(request, "health", settings.health_rate_limit_per_minute)
    return {"status": "ok", "service": settings.app_name}


@router.get("/couriers", response_model=list[CourierDescriptor])
async def list_couriers(request: Request, _: None = Depends(verify_shared_secret)):
    enforce_rate_limit(request, "couriers", settings.internal_rate_limit_per_minute)
    return registry.list_descriptors()


@router.post("/track", response_model=TrackingResult)
async def track(payload: TrackRequest, request: Request, _: None = Depends(verify_public_access)):
    enforce_rate_limit(request, "track", settings.track_rate_limit_per_minute)
    try:
        return await resolve_result(payload.courier, payload.trackingNumber, payload.autoDetect)
    except (CourierNotSupportedError, InvalidTrackingNumberError) as error:
        logger.warning("Track request rejected for courier=%s tracking=%s: %s", payload.courier, payload.trackingNumber, error)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except TrackingError as error:
        logger.error("TrackingError for courier=%s tracking=%s: %s", payload.courier, payload.trackingNumber, error)
        raise HTTPException(status_code=502, detail="Tracking details are temporarily unavailable right now.") from error
    except Exception as error:
        logger.exception("Unexpected tracking failure for courier=%s tracking=%s", payload.courier, payload.trackingNumber)
        raise HTTPException(status_code=502, detail="Tracking details are temporarily unavailable right now.") from error


@router.post("/bulk-track", response_model=list[TrackingResult])
async def bulk_track(payload: BulkTrackRequest, request: Request, _: None = Depends(verify_public_access)):
    enforce_rate_limit(request, "bulk-track", settings.bulk_rate_limit_per_minute)
    if len(payload.trackingNumbers) > settings.bulk_limit:
        raise HTTPException(status_code=400, detail=f"Bulk limit is {settings.bulk_limit}.")

    semaphore = asyncio.Semaphore(settings.max_bulk_concurrency)

    async def run_one(tracking_number: str) -> TrackingResult:
        async with semaphore:
            try:
                return await resolve_result(payload.courier, tracking_number, payload.autoDetect)
            except Exception as error:
                logger.warning("Bulk tracking failed for courier=%s tracking=%s: %s", payload.courier, tracking_number, error)
                return TrackingResult(
                    courier=payload.courier or "Auto detect",
                    trackingNumber=tracking_number,
                    success=False,
                    error="Tracking details are temporarily unavailable right now.",
                    strategy="error"
                )

    return await asyncio.gather(*(run_one(number) for number in payload.trackingNumbers))


@router.get("/internal/couriers", response_model=list[InternalCourierStatus])
async def internal_courier_status(request: Request, _: None = Depends(verify_shared_secret)):
    enforce_rate_limit(request, "internal-couriers", settings.internal_rate_limit_per_minute)
    return [
        InternalCourierStatus(
            id=adapter.id,
            metrics=adapter.metrics,
            enabled=adapter.enabled,
            strategies=adapter.strategy_priority
        )
        for adapter in registry.adapters.values()
    ]
