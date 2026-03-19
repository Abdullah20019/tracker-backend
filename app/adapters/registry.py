from __future__ import annotations

from app.adapters.base import CourierAdapter
from app.adapters.couriers.daewoo import DaewooAdapter
from app.adapters.couriers.blueex import BlueExAdapter
from app.adapters.couriers.disabled_adapter import DisabledCourierAdapter
from app.adapters.couriers.leopards import LeopardsAdapter
from app.adapters.couriers.mp import MPAdapter
from app.adapters.couriers.pakpost import PakistanPostAdapter
from app.adapters.couriers.postex import PostExAdapter
from app.adapters.couriers.tcs import TCSAdapter
from app.adapters.couriers.trax import TraxAdapter
from app.core.config import get_settings
from app.core.errors import CourierNotSupportedError


class CourierRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        self.adapters: dict[str, CourierAdapter] = {
            "tcs": TCSAdapter(enabled=settings.tcs_enabled),
            "pakpost": PakistanPostAdapter(enabled=settings.pakpost_enabled),
            "daewoo": DaewooAdapter(enabled=settings.daewoo_enabled),
            "leopards": LeopardsAdapter(enabled=settings.leopards_enabled),
            "postex": PostExAdapter(enabled=settings.postex_enabled),
            "mp": MPAdapter(enabled=settings.mp_enabled),
            "blueex": BlueExAdapter(enabled=settings.blueex_enabled),
            "trax": TraxAdapter(enabled=settings.trax_enabled),
        }

    def list_descriptors(self):
        return [adapter.descriptor() for adapter in self.adapters.values()]

    def detect(self, tracking_number: str) -> CourierAdapter:
        for adapter in self.adapters.values():
            if adapter.enabled and adapter.detect(tracking_number):
                return adapter
        raise CourierNotSupportedError("Could not detect a supported courier for this tracking number.")

    def resolve(self, courier: str) -> CourierAdapter:
        key = courier.lower()
        if key == "callcourier":
            key = "postex"
        adapter = self.adapters.get(key)
        if not adapter:
            raise CourierNotSupportedError(f"Courier '{courier}' is not registered.")
        if not adapter.enabled:
            raise CourierNotSupportedError(f"Courier '{courier}' is not enabled yet.")
        return adapter


registry = CourierRegistry()
