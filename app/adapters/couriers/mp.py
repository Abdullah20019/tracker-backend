from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup
import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.schemas import ProgressStep, ShipmentDetails, TrackingEvent, TrackingResult


class MPAdapter(CourierAdapter):
    id = "mp"
    name = "M&P"
    strategy_priority = ["html"]
    tracking_url_template = "https://www.mulphilog.com/tracking/{tracking_number}"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        normalized = re.sub(r"\W", "", tracking_number)
        return bool(re.fullmatch(r"\d{10,18}", normalized))

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = re.sub(r"\W", "", tracking_number)
        if not self.detect(normalized):
            raise InvalidTrackingNumberError("Invalid M&P tracking number.")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.get(self.tracking_url_template.format(tracking_number=normalized))
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"M&P connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"M&P request failed: {error}") from error

        if response.status_code != 200:
            raise UpstreamTrackingError(f"M&P tracking page failed with status {response.status_code}.")

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_number: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "html.parser")
        page_text = " ".join(soup.get_text(" ", strip=True).split()).lower()

        if "no tracking record found" in page_text:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in M&P system.",
                strategy="html",
            )

        details = self._extract_details(soup)
        events = self._extract_events(soup)

        if not details and not events:
            raise UpstreamTrackingError("M&P page structure changed and no tracking details were parsed.")

        latest = events[0] if events else None
        shipment_details = ShipmentDetails(
            agentReferenceNumber=details.get("Order ID"),
            origin=details.get("From location"),
            destination=details.get("To location"),
            bookingDate=details.get("Booking Date"),
            shipper=details.get("From name"),
            consignee=details.get("To name"),
        )

        return TrackingResult(
            courier=self.name,
            trackingNumber=details.get("Consignment Number") or tracking_number,
            success=True,
            status=(latest.status if latest else None) or details.get("Status"),
            location=latest.location if latest else details.get("To location"),
            timestamp=latest.timestamp if latest else details.get("Booking Date"),
            events=events,
            strategy="html",
            shipmentDetails=shipment_details,
            customerMessage=latest.details if latest else None,
            progressSteps=self._build_progress_steps(events),
        )

    def _extract_details(self, soup: BeautifulSoup) -> dict[str, str]:
        details: dict[str, str] = {}
        for field in soup.select("label.form-label"):
            parent = field.parent
            if parent is None:
                continue

            parent_classes = parent.get("class", [])
            if "mb-3" in parent_classes or "consignment-box" in parent_classes:
                continue

            inputs = parent.select("input.form-control[readonly]")
            if not inputs:
                continue

            label = field.select_one("label.form-label")
            label_text = field.get_text(" ", strip=True)
            values = [input_tag.get("value", "").strip() for input_tag in inputs if input_tag.get("value")]
            if not values:
                continue

            if label_text == "From":
                details["From name"] = values[0]
                if len(values) > 1:
                    details["From location"] = values[1]
            elif label_text == "To":
                details["To name"] = values[0]
                if len(values) > 1:
                    details["To location"] = values[1]
            else:
                details[label_text] = values[0]

        return details

    def _extract_events(self, soup: BeautifulSoup) -> list[TrackingEvent]:
        events: list[TrackingEvent] = []
        for item in soup.select(".order-track-step"):
            date_block = item.select_one(".order-track-text-sub")
            status_block = item.select_one(".order-track-text-stat.status")
            if not date_block or not status_block:
                continue

            location_block = item.select_one(".order-track-text-stat.location")
            message_block = item.select_one(".order-track-text-stat.status-message")

            timestamp = " ".join(date_block.get_text(" ", strip=True).split())
            status = " ".join(status_block.get_text(" ", strip=True).split())
            location = " ".join(location_block.get_text(" ", strip=True).split()) if location_block else None
            details = " ".join(message_block.get_text(" ", strip=True).split()) if message_block else None

            events.append(
                TrackingEvent(
                    status=status,
                    location=location or None,
                    timestamp=timestamp or None,
                    details=details or None,
                )
            )

        events.sort(key=self._event_sort_key, reverse=True)
        return events

    def _event_sort_key(self, event: TrackingEvent) -> datetime:
        if not event.timestamp:
            return datetime.min

        for fmt in ("%d %b %Y %I:%M %p", "%d %b %Y %H:%M"):
            try:
                return datetime.strptime(event.timestamp, fmt)
            except ValueError:
                continue

        return datetime.min

    def _build_progress_steps(self, events: list[TrackingEvent]) -> list[ProgressStep]:
        labels = [
            ("Booked", ("booked",)),
            ("In Transit", ("in-transit", "in transit", "arrived at ops facility")),
            ("Reached Destination", ("reached at destination",)),
            ("Out for Delivery", ("out-for-delivery", "out for delivery")),
            ("Delivered", ("delivered",)),
        ]

        seen_statuses = [event.status.lower() for event in events]
        highest_active = -1
        for index, (_, needles) in enumerate(labels):
            if any(any(needle in status for needle in needles) for status in seen_statuses):
                highest_active = index

        return [
            ProgressStep(label=label, active=index <= highest_active and highest_active >= 0)
            for index, (label, _) in enumerate(labels)
        ]
