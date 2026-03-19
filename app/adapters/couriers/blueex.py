from __future__ import annotations

import re

from bs4 import BeautifulSoup
import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.schemas import ProgressStep, TrackingEvent, TrackingResult


class BlueExAdapter(CourierAdapter):
    id = "blueex"
    name = "BlueEx"
    strategy_priority = ["http", "html"]
    tracking_api_url = "https://www.blue-ex.com/assets/config/tracking/trackall.php"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        normalized = tracking_number.strip().upper()
        if re.fullmatch(r"\d{10}", normalized):
            return 4000000000 <= int(normalized) <= 6999999999
        return bool(re.fullmatch(r"CP\d{12}", normalized))

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = tracking_number.strip().upper()
        if not self.detect(normalized):
            raise InvalidTrackingNumberError("Invalid BlueEx tracking number.")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"},
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.post(
                    self.tracking_api_url,
                    data={"tracking_numbers[]": normalized, "type": "blueex"},
                )
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"BlueEx connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"BlueEx request failed: {error}") from error

        if response.status_code != 200:
            raise UpstreamTrackingError(f"BlueEx tracking request failed with status {response.status_code}.")

        if not response.text.strip():
            return TrackingResult(
                courier=self.name,
                trackingNumber=normalized,
                success=False,
                error="Tracking number not found in BlueEx system.",
                strategy="html",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_number: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(".trackingInformation")
        if not container:
            raise UpstreamTrackingError("BlueEx page structure changed and no tracking container was found.")

        label = container.select_one(".sngltrackno")
        progress_steps: list[ProgressStep] = []
        events: list[TrackingEvent] = []
        for item in container.select(".trackingResult li"):
            status = " ".join(item.get_text(" ", strip=True).split())
            if not status:
                continue
            progress_steps.append(ProgressStep(label=status, active="active" in (item.get("class") or [])))

        note = container.select_one(".trackinfoInner p")
        note_text = " ".join(note.get_text(" ", strip=True).split()) if note else None
        detail_paragraphs = container.select(".trackinfoInner p")
        detailed_events = [self._parse_detail_paragraph(item.get_text(" ", strip=True)) for item in detail_paragraphs[1:]]
        events = [event for event in detailed_events if event is not None]

        if not events:
            events = [TrackingEvent(status=step.label) for step in progress_steps]

        if not events:
            raise UpstreamTrackingError("BlueEx returned tracking markup without any progress steps.")

        latest_event = events[-1]
        current_status = latest_event.status
        current_location = next((event.location for event in reversed(events) if event.location), None)
        current_timestamp = latest_event.timestamp

        return TrackingResult(
            courier=self.name,
            trackingNumber=label.get_text(" ", strip=True) if label else tracking_number,
            success=True,
            status=current_status or "Tracking available",
            location=current_location,
            timestamp=current_timestamp,
            events=events,
            strategy="html",
            customerMessage=note_text or current_status or "BlueEx returned a progress snapshot without event timestamps.",
            progressSteps=progress_steps,
        )

    def _parse_detail_paragraph(self, text: str) -> TrackingEvent | None:
        normalized = " ".join(text.split())
        if not normalized:
            return None

        match = re.match(r"^(.*?)\s*-\s*(.*)$", normalized)
        if not match:
            return TrackingEvent(status=normalized)

        timestamp = match.group(1).strip()
        status_text = match.group(2).strip()
        location = None

        if "," in status_text and any(keyword in status_text.lower() for keyword in ("reached", "warehouse", "hub", "station")):
            parts = [part.strip() for part in status_text.rsplit(",", 1)]
            if len(parts) == 2 and parts[1]:
                status_text, location = parts[0], parts[1]
        elif " - " in status_text:
            parts = [part.strip() for part in status_text.rsplit(" - ", 1)]
            if len(parts) == 2 and parts[1]:
                status_text, location = parts[0], parts[1]

        return TrackingEvent(status=status_text, timestamp=timestamp, location=location)
