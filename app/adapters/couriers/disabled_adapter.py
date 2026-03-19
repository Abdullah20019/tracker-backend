from app.adapters.base import CourierAdapter
from app.core.schemas import TrackingResult


class DisabledCourierAdapter(CourierAdapter):
    async def track(self, tracking_number: str) -> TrackingResult:
        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=False,
            error="This courier adapter is configured but not enabled yet.",
            strategy="disabled"
        )

    def detect(self, tracking_number: str) -> bool:
        return False
