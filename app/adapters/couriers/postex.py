from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.schemas import ProgressStep, ShipmentDetails, TrackingEvent, TrackingResult


class PostExAdapter(CourierAdapter):
    id = "postex"
    name = "PostEx"
    strategy_priority = ["api"]
    tracking_api_url = "https://postex.pk/api/tracking-order"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        normalized = re.sub(r"\W", "", tracking_number)
        return bool(re.fullmatch(r"\d{10,18}", normalized))

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = re.sub(r"\W", "", tracking_number)
        if not self.detect(normalized):
            raise InvalidTrackingNumberError("Invalid PostEx tracking number.")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.post(self.tracking_api_url, json={"trackingNumber": normalized})
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"PostEx connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"PostEx request failed: {error}") from error

        if response.status_code != 200:
            raise UpstreamTrackingError(f"PostEx API request failed with status {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as error:
            raise UpstreamTrackingError("PostEx API returned invalid JSON.") from error

        return self._parse_payload(normalized, payload)

    def _parse_payload(self, tracking_number: str, payload: dict[str, Any]) -> TrackingResult:
        distribution = payload.get("dist")
        if not isinstance(distribution, dict):
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in PostEx system.",
                strategy="api",
            )

        history = distribution.get("transactionStatusHistory") or []
        events: list[TrackingEvent] = []
        for entry in history:
            if not isinstance(entry, dict):
                continue

            status = (entry.get("transactionStatusMessage") or "Unknown status").strip()
            timestamp = self._format_datetime(entry.get("modifiedDatetime"))
            location = self._extract_location(status)

            events.append(
                TrackingEvent(
                    status=status,
                    location=location,
                    timestamp=timestamp,
                    details=None,
                )
            )

        latest = events[0] if events else None
        latest_known_location = next((event.location for event in events if event.location), None)

        return TrackingResult(
            courier=self.name,
            trackingNumber=distribution.get("trackingNumber") or tracking_number,
            success=True,
            status=latest.status if latest else "Tracking available",
            location=latest.location or latest_known_location,
            timestamp=latest.timestamp if latest else self._format_datetime(distribution.get("orderPickupDate")),
            events=events,
            strategy="api",
            shipmentDetails=ShipmentDetails(
                bookingDate=self._format_datetime(distribution.get("orderPickupDate")),
                consignee=distribution.get("customerName"),
            ),
            customerMessage=latest.status if latest else None,
            progressSteps=self._build_progress_steps(events),
        )

    def _build_progress_steps(self, events: list[TrackingEvent]) -> list[ProgressStep]:
        labels = [
            ("Booked", ("warehouse", "postex. warehouse", "postex warehouse")),
            ("In Transit", ("departed", "arrived at transit hub", "received at")),
            ("Waiting for Delivery", ("waiting for delivery",)),
            ("Out for Delivery", ("enroute for delivery",)),
            ("Delivered", ("delivered to customer",)),
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

    def _format_datetime(self, value: str | None) -> str | None:
        if not value:
            return None

        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%d %b %Y %I:%M %p")
            except ValueError:
                continue

        return value

    def _extract_location(self, status: str) -> str | None:
        patterns = [
            r"Arrived at Transit Hub\s+(.+)$",
            r"Departed to\s+(.+)$",
            r"Received at\s+(.+?)\s+Warehouse$",
            r"At\s+(.+?)\s+Warehouse$",
        ]

        for pattern in patterns:
            match = re.search(pattern, status, re.IGNORECASE)
            if match:
                return match.group(1).strip(" .")

        return None
