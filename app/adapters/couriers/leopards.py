from __future__ import annotations

import re

from bs4 import BeautifulSoup
import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.http import get_http_client
from app.core.schemas import ProgressStep, ShipmentDetails, TrackingEvent, TrackingResult


class LeopardsAdapter(CourierAdapter):
    id = "leopards"
    name = "Leopards"
    strategy_priority = ["http", "html"]
    base_url = "https://leopardscourier.com"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        normalized = tracking_number.strip().upper()
        return bool(re.fullmatch(r"[A-Z0-9]{8,20}", normalized))

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = tracking_number.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{6,24}", normalized):
            raise InvalidTrackingNumberError("Invalid Leopards tracking number.")

        try:
            async with get_http_client() as client:
                landing = await client.get(f"{self.base_url}/tracking")
                if landing.status_code != 200:
                    raise UpstreamTrackingError(f"Leopards tracking page failed with status {landing.status_code}.")

                token_match = re.search(r"_token:\s*'([^']+)'", landing.text)
                payload = {"cn_number": normalized}
                if token_match:
                    payload["_token"] = token_match.group(1)

                await client.get(
                    f"{self.base_url}/shipment_tracking-new",
                    params=payload,
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                response = await client.get(
                    f"{self.base_url}/shipment_tracking_view",
                    params={"cn_number": normalized},
                )
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"Leopards connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"Leopards request failed: {error}") from error

        if response.status_code != 200:
            raise UpstreamTrackingError(f"Leopards tracking view failed with status {response.status_code}.")

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_number: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        lowered = text.lower()

        if "appeared to be invalid / record not found" in lowered:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in Leopards system.",
                strategy="html",
            )

        progress_steps = self._extract_progress_steps(soup)
        summary = self._extract_summary_table(soup)
        shipment_details = self._extract_shipment_details(soup)

        events: list[TrackingEvent] = []
        for item in soup.select(".tracking-item"):
            date_block = item.select_one(".tracking-date")
            content_block = item.select_one(".tracking-content")
            icon_block = item.select_one(".tracking-icon")
            timestamp = date_block.get_text(" ", strip=True) if date_block else None

            status = None
            location = None
            details = None
            if content_block:
                span = content_block.find("span")
                if span:
                    location = span.get_text(" ", strip=True) or None
                    span.extract()
                content_text = " ".join(content_block.get_text(" ", strip=True).split())
                status = content_text or None
            if not status and icon_block:
                status = " ".join(icon_block.get("class", [])) or None
            if status:
                events.append(
                    TrackingEvent(
                        status=status,
                        location=location,
                        timestamp=timestamp,
                        details=details,
                    )
                )

        self._fill_missing_route_details(shipment_details, events)

        current_status = next((step.label for step in reversed(progress_steps) if step.active), None)
        if not current_status:
            current_status = summary.get("currentStatus") or (events[0].status if events else None)
        if not current_status and not events:
            raise UpstreamTrackingError("Leopards page structure changed and no tracking details were parsed.")

        latest_event = events[0] if events else None
        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=True,
            status=current_status or (latest_event.status if latest_event else None),
            location=shipment_details.destination or (latest_event.location if latest_event else None),
            timestamp=summary.get("dated") or (latest_event.timestamp if latest_event else None),
            events=events,
            strategy="html",
            shipmentDetails=ShipmentDetails(
                agentReferenceNumber=shipment_details.reference_no,
                origin=shipment_details.origin,
                destination=shipment_details.destination,
                bookingDate=shipment_details.booking_date,
                shipper=shipment_details.shipper,
                consignee=shipment_details.consignee,
                pieces=shipment_details.pieces,
                signedForBy=summary.get("signedForBy"),
            ),
            customerMessage=summary.get("currentStatus"),
            progressSteps=progress_steps,
        )

    def _extract_progress_steps(self, soup: BeautifulSoup) -> list[ProgressStep]:
        steps: list[ProgressStep] = []
        for item in soup.select("#bar-progress .step"):
            raw = " ".join(item.get_text(" ", strip=True).split())
            label = re.sub(r"^\d+\s*", "", raw).strip()
            if not label:
                continue
            steps.append(ProgressStep(label=label, active="step-active" in (item.get("class") or [])))
        return steps

    def _extract_summary_table(self, soup: BeautifulSoup) -> dict[str, str]:
        summary: dict[str, str] = {}
        for table in soup.select("table.table.table-striped.table-bordered"):
            header = table.find("th")
            if not header:
                continue
            heading = " ".join(header.get_text(" ", strip=True).split())
            if heading.lower() == "shipment information":
                continue
            if heading.lower() == "shipment detail":
                continue

            summary["currentStatus"] = heading
            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                pairs = ((cells[0], cells[1]), (cells[2], cells[3]))
                for key_cell, value_cell in pairs:
                    key = " ".join(key_cell.get_text(" ", strip=True).split()).rstrip(":").strip()
                    value = " ".join(value_cell.get_text(" ", strip=True).split())
                    if not key or not value:
                        continue
                    if key.lower() == "signed for by":
                        summary["signedForBy"] = value
                    elif key.lower() == "dated":
                        summary["dated"] = value
            if summary:
                return summary
        return summary

    def _extract_shipment_details(self, soup: BeautifulSoup) -> "_LeopardsShipmentDetails":
        details = _LeopardsShipmentDetails()
        for table in soup.select("table.table.table-striped.table-bordered"):
            header_cell = table.find("td", attrs={"colspan": True})
            if not header_cell:
                continue
            heading = " ".join(header_cell.get_text(" ", strip=True).split())
            if heading.lower() != "shipment detail":
                continue

            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                pairs = []
                if len(cells) >= 2:
                    pairs.append((cells[0], cells[1]))
                if len(cells) >= 4:
                    pairs.append((cells[2], cells[3]))

                for key_cell, value_cell in pairs:
                    key = " ".join(key_cell.get_text(" ", strip=True).split()).rstrip(":").strip()
                    value = " ".join(value_cell.get_text(" ", strip=True).split())
                    if not key or not value:
                        continue
                    if key.lower() == "origin":
                        details.origin = value
                    elif key.lower() == "destination":
                        details.destination = value
                    elif key.lower() == "shipper":
                        details.shipper = value
                    elif key.lower() == "consignee":
                        details.consignee = value
                    elif key.lower() == "reference no.":
                        details.reference_no = value
                    elif key.lower() == "booking date":
                        details.booking_date = value
                    elif key.lower() == "pieces":
                        details.pieces = value
            return details
        return details

    def _fill_missing_route_details(
        self,
        details: "_LeopardsShipmentDetails",
        events: list[TrackingEvent],
    ) -> None:
        if details.origin and details.destination:
            return

        for event in events:
            status = (event.status or "").upper()
            location = (event.location or "").upper()

            if not details.origin:
                origin_match = re.search(r"\bORIGIN\s+([A-Z][A-Z\s]+)$", status)
                if origin_match:
                    details.origin = " ".join(origin_match.group(1).split())

            if not details.origin or not details.destination:
                route_match = re.search(r"\bFROM\s+([A-Z][A-Z\s]+?)\s+TO\s+([A-Z][A-Z\s]+?)(?:\s|$)", status)
                if route_match:
                    if not details.origin:
                        details.origin = " ".join(route_match.group(1).split())
                    if not details.destination:
                        details.destination = " ".join(route_match.group(2).split())

            if not details.destination:
                assigned_match = re.search(r"\bIN\s+([A-Z][A-Z\s]+)$", status)
                if assigned_match:
                    details.destination = " ".join(assigned_match.group(1).split())
                elif location:
                    details.destination = " ".join(location.split())

            if details.origin and details.destination:
                return


class _LeopardsShipmentDetails:
    def __init__(self) -> None:
        self.origin: str | None = None
        self.destination: str | None = None
        self.shipper: str | None = None
        self.consignee: str | None = None
        self.reference_no: str | None = None
        self.booking_date: str | None = None
        self.pieces: str | None = None
