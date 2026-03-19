from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup
import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.http import get_http_client
from app.core.schemas import ShipmentDetails, TrackingEvent, TrackingResult


class PakistanPostAdapter(CourierAdapter):
    id = "pakpost"
    name = "Pakistan Post"
    strategy_priority = ["http", "html", "lightpanda", "edge"]
    prefixes = ("UMS", "RGL", "PAR", "COD", "EMS", "VPL", "VPP")
    base_url = "https://ep.gov.pk/emtts/EPTrack_Live.aspx"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        normalized = tracking_number.upper().strip()
        return normalized.startswith(self.prefixes)

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = tracking_number.upper().strip()
        if not self.detect(normalized):
            raise InvalidTrackingNumberError("Invalid Pakistan Post tracking number.")

        try:
            async with get_http_client() as client:
                response = await client.get(f"{self.base_url}?ArticleIDz={normalized}")
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"Pakistan Post connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"Pakistan Post request failed: {error}") from error
        if response.status_code != 200:
            raise UpstreamTrackingError(f"Pakistan Post request failed with status {response.status_code}.")

        soup = BeautifulSoup(response.text, "html.parser")
        text_lower = soup.get_text(" ", strip=True).lower()
        if any(phrase in text_lower for phrase in ("not found", "no record", "invalid article")):
            return TrackingResult(
                courier=self.name,
                trackingNumber=normalized,
                success=False,
                error="Tracking number not found in Pakistan Post system.",
                strategy="http"
            )

        history = self._extract_history(soup)
        return self._parse_result(normalized, soup, history)

    def _extract_history(self, soup: BeautifulSoup) -> list[TrackingEvent]:
        history_container = soup.find(id="TrackDetailDiv")
        if not history_container:
            return []

        history: list[TrackingEvent] = []
        seen: set[tuple[str | None, str | None, str]] = set()
        current_date: str | None = None
        time_pattern = re.compile(r"\d{1,2}:\d{2}\s*(?:AM|PM)", re.IGNORECASE)
        for row in history_container.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if not cells:
                continue
            if len(cells) == 1 and re.search(r"\d{4}", cells[0]) and not time_pattern.search(cells[0]):
                current_date = cells[0]
                continue
            if not current_date:
                continue

            time_value = next((cell for cell in cells if time_pattern.search(cell)), None)
            if not time_value:
                continue

            time_index = cells.index(time_value)
            office = cells[time_index + 1] if len(cells) > time_index + 1 else None
            status = cells[time_index + 2] if len(cells) > time_index + 2 else office or "In transit"
            event = TrackingEvent(
                status=status,
                location=office,
                timestamp=f"{current_date} {time_value}".strip()
            )
            dedupe_key = (event.timestamp, event.location, event.status)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            history.append(event)

        history.sort(key=self._history_sort_key, reverse=True)
        return history

    def _extract_label_value(self, soup: BeautifulSoup, element_id: str) -> str | None:
        element = soup.find(id=element_id)
        if not element:
            return None
        value = element.get_text(" ", strip=True)
        return value or None

    def _parse_result(self, tracking_number: str, soup: BeautifulSoup, history: list[TrackingEvent]) -> TrackingResult:
        latest = history[0] if history else None

        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=True,
            status=latest.status if latest else "In transit",
            location=latest.location if latest else self._extract_label_value(soup, "LblDeliveryOffice"),
            timestamp=latest.timestamp if latest else None,
            events=history,
            strategy="http",
            shipmentDetails=ShipmentDetails(
                origin=self._extract_label_value(soup, "LblBookingOffice"),
                destination=self._extract_label_value(soup, "LblDeliveryOffice"),
            ),
        )

    def _history_sort_key(self, event: TrackingEvent) -> datetime:
        if not event.timestamp:
            return datetime.min

        for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p"):
            try:
                return datetime.strptime(event.timestamp, fmt)
            except ValueError:
                continue
        return datetime.min
