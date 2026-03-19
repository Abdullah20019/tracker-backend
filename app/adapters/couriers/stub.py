from app.adapters.base import CourierAdapter
from app.core.schemas import TrackingResult


class StubCourierAdapter(CourierAdapter):
    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        return False

    async def track(self, tracking_number: str) -> TrackingResult:
        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=False,
            error=f"{self.name} live integration is not configured yet.",
            strategy="unavailable"
        )


class LeopardsAdapter(StubCourierAdapter):
    id = "leopards"
    name = "Leopards"
    strategy_priority = ["http", "html", "lightpanda", "edge"]


class PostExAdapter(StubCourierAdapter):
    id = "postex"
    name = "PostEx"
    strategy_priority = ["http", "html", "lightpanda", "edge"]


class MPAdapter(StubCourierAdapter):
    id = "mp"
    name = "M&P"
    strategy_priority = ["http", "html", "lightpanda", "edge"]


class BlueExAdapter(StubCourierAdapter):
    id = "blueex"
    name = "BlueEx"
    strategy_priority = ["http", "html", "lightpanda", "edge"]


class CallCourierAdapter(StubCourierAdapter):
    id = "callcourier"
    name = "Call Courier"
    strategy_priority = ["http", "html", "lightpanda", "edge"]


class TraxAdapter(StubCourierAdapter):
    id = "trax"
    name = "Trax"
    strategy_priority = ["http", "html", "lightpanda", "edge"]
