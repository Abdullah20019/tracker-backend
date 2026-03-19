from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from app.adapters.base import CourierAdapter
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.schemas import ProgressStep, ShipmentDetails, TrackingEvent, TrackingResult


class DaewooAdapter(CourierAdapter):
    id = "daewoo"
    name = "Daewoo"
    strategy_priority = ["api"]
    tracking_api_url = "https://careconnectapi.daewoo.net.pk:4432/api/Tracking/GetTrackingDetailsFastExByCN"

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def detect(self, tracking_number: str) -> bool:
        return False

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = re.sub(r"\W", "", tracking_number)
        if not re.fullmatch(r"\d{8,12}", normalized):
            raise InvalidTrackingNumberError("Invalid Daewoo consignment number.")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.get(
                    self.tracking_api_url,
                    params={"ConsignmentId": normalized},
                )
        except httpx.ConnectError as error:
            raise UpstreamTrackingError(f"Daewoo connection failed: {error}") from error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"Daewoo request failed: {error}") from error

        if response.status_code not in (200, 400):
            raise UpstreamTrackingError(f"Daewoo API request failed with status {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as error:
            raise UpstreamTrackingError("Daewoo API returned invalid JSON.") from error

        return self._parse_payload(normalized, payload)

    def _parse_payload(self, tracking_number: str, payload: dict[str, Any]) -> TrackingResult:
        status_code = payload.get("StatusCode")
        title = payload.get("Title")
        booking = payload.get("BookingDetails")

        if status_code == 400:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error=title or "Daewoo tracking is only available for recent bookings.",
                strategy="api",
            )

        if not isinstance(booking, dict):
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in Daewoo system.",
                strategy="api",
            )

        history = booking.get("hdTrackingDetail") or []
        sender = self._extract_contact(booking.get("senderDetails"))
        receiver = self._extract_contact(booking.get("receiverDetail"))
        customer = self._extract_contact(booking.get("customerDetails"))
        order_information = booking.get("orderinformation") or []
        order = order_information[0] if order_information and isinstance(order_information[0], dict) else {}

        if not history and not booking.get("consignmentNo"):
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="No live Daewoo tracking details were found for this consignment.",
                strategy="api",
            )

        events: list[TrackingEvent] = []
        for entry in history:
            if not isinstance(entry, dict):
                continue
            status = self._clean_status(entry.get("status") or entry.get("reason") or "Unknown status")
            source = entry.get("source")
            destination = entry.get("destination")
            reason = entry.get("reason")
            details = None
            if reason and reason.strip() and reason.strip().lower() not in status.lower():
                details = reason.strip()

            events.append(
                TrackingEvent(
                    status=status,
                    location=source or destination,
                    timestamp=self._format_datetime(entry.get("dateTime")),
                    details=details,
                )
            )

        latest = events[0] if events else None
        latest_location = latest.location if latest and latest.location else booking.get("dtn")
        booking_identifier = booking.get("booking_id") or booking.get("consignmentNo") or tracking_number

        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=True,
            status=latest.status if latest else booking.get("status_name") or "Tracking available",
            location=latest_location,
            timestamp=latest.timestamp if latest else self._format_datetime(booking.get("booking_datetime")),
            events=events,
            strategy="api",
            shipmentDetails=ShipmentDetails(
                agentReferenceNumber=str(booking_identifier) if booking_identifier is not None else None,
                trackingCode=str(booking.get("track_code")) if booking.get("track_code") is not None else None,
                origin=self._compose_station(booking.get("stn"), booking.get("sccpn")),
                destination=self._compose_station(booking.get("dtn"), booking.get("dccpn")),
                bookingDate=self._format_datetime(booking.get("booking_datetime")),
                pieces=str(booking.get("tpieces")) if booking.get("tpieces") is not None else None,
                consignee=receiver.get("name") or customer.get("name"),
                shipper=sender.get("name") or customer.get("name"),
                signedForBy=receiver.get("name"),
                deliveryType=order.get("sType") or booking.get("customer_group_name"),
                reason=latest.details if latest and latest.details else None,
                senderAddress=sender.get("address"),
                senderPhone=sender.get("phone"),
                receiverAddress=receiver.get("address"),
                receiverPhone=receiver.get("phone"),
            ),
            customerMessage=title or (latest.details if latest else None),
            progressSteps=self._build_progress_steps(events),
        )

    def _build_progress_steps(self, events: list[TrackingEvent]) -> list[ProgressStep]:
        labels = [
            ("Booked", ("book", "booking")),
            ("On Route", ("on route", "in transit", "transit")),
            ("At Terminal", ("terminal", "hub", "station")),
            ("Out for Delivery", ("out for delivery", "delivery")),
            ("Delivered", ("delivered",)),
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
        if not value or value == "0001-01-01T00:00:00":
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%d %b %Y %I:%M %p")
            except ValueError:
                continue
        return value

    def _clean_status(self, value: str) -> str:
        normalized = " ".join(value.split())
        parts = [part.strip(" -") for part in normalized.split(" - ") if part.strip(" -")]
        if len(parts) >= 2 and parts[-1].lower() == parts[-2].lower():
            parts = parts[:-1]
        return " - ".join(parts) if parts else normalized

    def _extract_name(self, value: Any) -> str | None:
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                for key in ("name", "customerName", "receiverName", "senderName"):
                    if first.get(key):
                        return str(first[key])
        return None

    def _extract_contact(self, value: Any) -> dict[str, str | None]:
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                name = first.get("name") or first.get("person") or first.get("customerName")
                phone = first.get("phoneNo") or first.get("phone")
                address = first.get("address")
                return {
                    "name": str(name).strip() if name else None,
                    "phone": str(phone).strip() if phone else None,
                    "address": str(address).strip() if address else None,
                }
        return {"name": None, "phone": None, "address": None}

    def _compose_station(self, city: Any, branch: Any) -> str | None:
        city_value = str(city).strip() if city else ""
        branch_value = str(branch).strip() if branch else ""
        if city_value and branch_value:
            return f"{city_value} - {branch_value}"
        return city_value or branch_value or None
