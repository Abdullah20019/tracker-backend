from __future__ import annotations

import re
from typing import Any

import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.schemas import ProgressStep, ShipmentDetails, TrackingEvent, TrackingResult


class TraxAdapter(CourierAdapter):
    id = "trax"
    name = "Trax"
    strategy_priority = ["api"]
    tracking_page_url = "https://sonic.pk/tracking"
    tracking_api_url = "https://sonic.pk/tracking/track"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        return False

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = tracking_number.strip()
        if not re.fullmatch(r"\d{6,24}", normalized):
            raise InvalidTrackingNumberError("Invalid Trax tracking number.")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=httpx.Timeout(15.0),
            ) as client:
                page = await client.get(self.tracking_page_url)
                if page.status_code != 200:
                    raise UpstreamTrackingError(f"Trax tracking page failed with status {page.status_code}.")

                token_match = re.search(r"'_token': '([^']+)'", page.text)
                if not token_match:
                    raise UpstreamTrackingError("Trax CSRF token was not found on the tracking page.")

                response = await client.post(
                    self.tracking_api_url,
                    data={
                        "tracking_numbers": normalized,
                        "_token": token_match.group(1),
                    },
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.tracking_page_url},
                )
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"Trax connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"Trax request failed: {error}") from error

        if response.status_code != 200:
            raise UpstreamTrackingError(f"Trax API request failed with status {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as error:
            raise UpstreamTrackingError("Trax API returned invalid JSON.") from error

        return self._parse_payload(normalized, payload)

    def _parse_payload(self, tracking_number: str, payload: dict[str, Any]) -> TrackingResult:
        invalid_numbers = payload.get("invalid") or []
        if tracking_number in invalid_numbers:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in Trax system.",
                strategy="api",
            )

        shipments = payload.get("shipments") or {}
        if not shipments:
            raise UpstreamTrackingError("Trax API returned no shipments and no explicit invalid result.")

        shipment = next(iter(shipments.values()))
        history = shipment.get("tracking_history") or []
        events: list[TrackingEvent] = []
        for entry in history:
            if not isinstance(entry, dict):
                continue
            details = entry.get("details") or entry.get("remarks")
            events.append(
                TrackingEvent(
                    status=entry.get("status") or "Unknown status",
                    location=entry.get("location"),
                    timestamp=entry.get("date_time"),
                    details=details,
                )
            )
        latest = events[0] if events else None
        latest_location = next((event.location for event in events if event.location), None)
        shipment_details = ShipmentDetails(
            origin=self._nested_value(shipment, "pickup", "origin"),
            destination=self._nested_value(shipment, "consignee", "destination"),
            shipper=self._nested_value(shipment, "shipper", "name"),
            consignee=self._nested_value(shipment, "consignee", "name"),
        )

        return TrackingResult(
            courier=self.name,
            trackingNumber=shipment.get("tracking_number") or tracking_number,
            success=True,
            status=latest.status if latest else "In transit",
            location=(latest.location if latest and latest.location else latest_location or shipment_details.destination),
            timestamp=latest.timestamp if latest else None,
            events=events,
            strategy="api",
            shipmentDetails=shipment_details,
            customerMessage=latest.details if latest and latest.details else latest.status if latest else None,
            progressSteps=self._build_progress_steps(events),
        )

    def _build_progress_steps(self, events: list[TrackingEvent]) -> list[ProgressStep]:
        labels = [
            ("Picked Up", ("pickup", "picked", "booked")),
            ("In Transit", ("transit", "departed", "arrived", "bagging", "manifested", "forwarded")),
            ("At Destination", ("destination", "arrival at destination", "reached destination")),
            ("Out for Delivery", ("out for delivery", "delivery sheet", "with rider")),
            ("Delivered", ("delivered", "received by consignee")),
        ]

        statuses = [event.status.lower() for event in events]
        highest_active = -1
        for index, (_, needles) in enumerate(labels):
            if any(any(needle in status for needle in needles) for status in statuses):
                highest_active = index

        return [
            ProgressStep(label=label, active=index <= highest_active and highest_active >= 0)
            for index, (label, _) in enumerate(labels)
        ]

    def _nested_value(self, payload: dict[str, Any], *keys: str) -> str | None:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        if current is None:
            return None

        value = str(current).strip()
        return value or None
