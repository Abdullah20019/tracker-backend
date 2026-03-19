from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from time import perf_counter

from app.core.schemas import CourierDescriptor, TrackingResult


class CourierAdapter(ABC):
    id: str = ""
    name: str = ""
    enabled: bool = False
    supports_bulk: bool = True
    strategy_priority: list[str] = []

    def __init__(self) -> None:
        self.metrics: dict[str, float] = defaultdict(float)

    @abstractmethod
    def detect(self, tracking_number: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def track(self, tracking_number: str) -> TrackingResult:
        raise NotImplementedError

    def normalize(self, result: TrackingResult) -> TrackingResult:
        return result

    def descriptor(self) -> CourierDescriptor:
        return CourierDescriptor(
            id=self.id,
            name=self.name,
            enabled=self.enabled,
            supportsBulk=self.supports_bulk,
            strategyPriority=self.strategy_priority
        )

    def mark_latency(self, seconds: float) -> None:
        total = self.metrics.get("latency_total", 0.0) + seconds
        count = self.metrics.get("latency_count", 0.0) + 1
        self.metrics["latency_total"] = total
        self.metrics["latency_count"] = count
        self.metrics["latency_avg"] = total / count

    async def timed_track(self, tracking_number: str) -> TrackingResult:
        started = perf_counter()
        result = await self.track(tracking_number)
        self.mark_latency(perf_counter() - started)
        return result
