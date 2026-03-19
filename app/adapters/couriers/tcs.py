from __future__ import annotations

import asyncio
import re
from typing import Any

from bs4 import BeautifulSoup
import httpx

from app.adapters.base import CourierAdapter
from app.browsers.manager import BrowserManager
from app.core.errors import InvalidTrackingNumberError, UpstreamTrackingError
from app.core.http import get_http_client
from app.core.schemas import ShipmentDetails, TrackingEvent, TrackingResult


class TCSAdapter(CourierAdapter):
    id = "tcs"
    name = "TCS"
    strategy_priority = ["api", "light-fallback", "rendered-html"]
    api_url = "https://www.tcsexpress.com/apibridge"
    track_url = "https://www.tcsexpress.com/track/"
    api_timeout_seconds = 6.0
    warm_timeout_seconds = 5.0

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled
        self.browser_manager = BrowserManager()

    def detect(self, tracking_number: str) -> bool:
        normalized = re.sub(r"\D", "", tracking_number)
        return len(normalized) in (12, 13)

    async def track(self, tracking_number: str) -> TrackingResult:
        normalized = re.sub(r"\D", "", tracking_number)
        if not self.detect(normalized):
            raise InvalidTrackingNumberError("Invalid TCS tracking number.")

        try:
            payload = await self._fetch_api_payload(normalized)
            result = self._parse_api_response(normalized, payload)
            if result.success:
                return result

            rendered_result = await self._try_rendered_page_fallback(normalized)
            return rendered_result or result
        except UpstreamTrackingError as error:
            rendered_result = await self._try_rendered_page_fallback(normalized)
            if rendered_result:
                return rendered_result
            raise error

    async def _fetch_api_payload(self, tracking_number: str) -> dict[str, Any]:
        try:
            async with get_http_client() as client:
                data = await self._request_api_payload(client, tracking_number)
                if self._has_usable_response(data):
                    return data

                await self._warm_track_session(client, tracking_number)
                data = await self._request_api_payload(client, tracking_number, browser_like=True)
                if self._has_usable_response(data):
                    return data
                raise UpstreamTrackingError("TCS API returned no usable tracking details.")
        except httpx.ReadTimeout as error:
            raise UpstreamTrackingError("TCS API timed out. Please try again in a moment.") from error
        except httpx.ConnectError as error:
            if "CERTIFICATE_VERIFY_FAILED" not in str(error):
                raise UpstreamTrackingError("TCS API connection failed. Please try again in a moment.") from error

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.api_timeout_seconds),
                    follow_redirects=True,
                    verify=False,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132 Safari/537.36"
                        )
                    }
                ) as client:
                    data = await self._request_api_payload(client, tracking_number)
                    if self._has_usable_response(data):
                        return data

                    await self._warm_track_session(client, tracking_number)
                    data = await self._request_api_payload(client, tracking_number, browser_like=True)
                    if self._has_usable_response(data):
                        return data
                    raise UpstreamTrackingError("TCS API returned no usable tracking details.")
            except httpx.ReadTimeout as retry_error:
                raise UpstreamTrackingError("TCS API timed out after SSL fallback. Please try again in a moment.") from retry_error
            except httpx.HTTPError as retry_error:
                raise UpstreamTrackingError(
                    f"TCS API request failed after SSL fallback: {self._describe_http_error(retry_error)}"
                ) from retry_error
        except httpx.HTTPError as error:
            raise UpstreamTrackingError(f"TCS API request failed: {self._describe_http_error(error)}") from error

    async def _request_api_payload(
        self,
        client: httpx.AsyncClient,
        tracking_number: str,
        *,
        browser_like: bool = False,
    ) -> dict[str, Any]:
        payload = self._build_payload(tracking_number, browser_like=browser_like)
        response = await client.post(
            self.api_url,
            json=payload,
            headers=self._request_headers(tracking_number, browser_like=browser_like),
            timeout=httpx.Timeout(self.api_timeout_seconds),
        )
        if response.status_code != 200:
            raise UpstreamTrackingError(f"TCS API request failed with status {response.status_code}.")

        try:
            data = response.json()
        except ValueError as error:
            raise UpstreamTrackingError("TCS API returned invalid JSON.") from error

        if not isinstance(data, dict) or "responseData" not in data:
            raise UpstreamTrackingError("TCS API response format was not recognized.")

        if self._has_usable_response(data) or not self._is_transient_empty_response(data):
            return data

        raise UpstreamTrackingError("TCS API returned no usable tracking details.")

    def _build_payload(self, tracking_number: str, *, browser_like: bool) -> dict[str, Any]:
        session_headers = self._request_headers(tracking_number, browser_like=browser_like) if browser_like else {}
        return {
            "body": {
                "url": "trackapinew",
                "type": "GET",
                "headers": session_headers,
                "payload": {},
                "param": f"consignee={tracking_number}",
            }
        }

    def _request_headers(self, tracking_number: str, *, browser_like: bool) -> dict[str, str]:
        if not browser_like:
            return {}
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": "https://www.tcsexpress.com",
            "Referer": f"{self.track_url}{tracking_number}",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def _warm_track_session(self, client: httpx.AsyncClient, tracking_number: str) -> None:
        try:
            await client.get(
                f"{self.track_url}{tracking_number}",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://www.tcsexpress.com/",
                },
                timeout=httpx.Timeout(self.warm_timeout_seconds),
            )
        except httpx.HTTPError:
            return

    def _has_usable_response(self, payload: dict[str, Any]) -> bool:
        response_data = payload.get("responseData")
        if not isinstance(response_data, dict):
            return False

        shipment_info = response_data.get("shipmentinfo") or []
        delivery_info = response_data.get("deliveryinfo") or []
        checkpoints = response_data.get("checkpoints") or []
        shipment_summary = (response_data.get("shipmentsummary") or "").lower()

        if "no data found" in shipment_summary or "invalid cn" in shipment_summary:
            return True

        return bool(shipment_info or delivery_info or checkpoints)

    def _is_transient_empty_response(self, payload: dict[str, Any]) -> bool:
        response_data = payload.get("responseData")
        if not isinstance(response_data, dict):
            return False
        shipment_summary = (response_data.get("shipmentsummary") or "").lower()
        if "no data found" in shipment_summary or "invalid cn" in shipment_summary:
            return False
        shipment_info = response_data.get("shipmentinfo") or []
        delivery_info = response_data.get("deliveryinfo") or []
        checkpoints = response_data.get("checkpoints") or []
        return not shipment_info and not delivery_info and not checkpoints

    def _describe_http_error(self, error: httpx.HTTPError) -> str:
        message = str(error).strip()
        if message:
            return message
        if isinstance(error, httpx.ReadTimeout):
            return "request timed out"
        if isinstance(error, httpx.ConnectError):
            return "connection failed"
        return error.__class__.__name__

    def _parse_api_response(self, tracking_number: str, payload: dict[str, Any]) -> TrackingResult:
        response_data = payload.get("responseData")
        if not isinstance(response_data, dict):
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in TCS system.",
                strategy="api",
            )

        shipment_info = response_data.get("shipmentinfo") or []
        delivery_info = response_data.get("deliveryinfo") or []
        checkpoints = response_data.get("checkpoints") or []
        shipment_summary = response_data.get("shipmentsummary")

        summary_lower = (shipment_summary or "").lower()
        if "no data found" in summary_lower or "invalid cn" in summary_lower:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in TCS system.",
                strategy="api",
            )

        if not shipment_info and not delivery_info and not checkpoints:
            return TrackingResult(
                courier=self.name,
                trackingNumber=tracking_number,
                success=False,
                error="Tracking number not found in TCS system.",
                strategy="api",
            )

        shipment_row = shipment_info[0] if shipment_info else {}
        delivery_row = delivery_info[0] if delivery_info else {}
        events = [
            TrackingEvent(
                status=checkpoint.get("status") or "Unknown status",
                location=checkpoint.get("recievedby"),
                timestamp=checkpoint.get("datetime"),
                details=None,
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, dict)
        ]

        status = delivery_row.get("status") or (events[0].status if events else None)
        location = delivery_row.get("station") or shipment_row.get("destination")
        timestamp = delivery_row.get("datetime") or (events[0].timestamp if events else shipment_row.get("bookingdate"))

        return TrackingResult(
            courier=self.name,
            trackingNumber=shipment_row.get("consignmentno") or tracking_number,
            success=True,
            status=status,
            location=location,
            timestamp=timestamp,
            events=events,
            error=None,
            strategy="api",
            shipmentDetails=ShipmentDetails(
                agentReferenceNumber=shipment_row.get("referenceno") or shipment_row.get("shipper"),
                origin=shipment_row.get("origin"),
                destination=shipment_row.get("destination"),
                bookingDate=shipment_row.get("bookingdate"),
                shipper=shipment_row.get("shipper"),
            ),
            customerMessage=shipment_summary,
        )

    async def _try_rendered_page_fallback(self, tracking_number: str) -> TrackingResult | None:
        url = f"{self.track_url}{tracking_number}"
        try:
            html = await self.browser_manager._run_chromium(url)
        except Exception:
            return None

        return self._parse_rendered_html(tracking_number, html)

    def _parse_rendered_html(self, tracking_number: str, html: str) -> TrackingResult | None:
        html_lower = html.lower()
        if "no record found" in html_lower or "no shipment found" in html_lower:
            return None
        if "shipment booking details" not in html_lower and "shipment track summary" not in html_lower:
            return None

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        compact = " ".join(text.split())

        agent_reference = self._extract_field(
            compact,
            "Agent Reference Number",
            ("Origin:", "Destination:", "Booking Date:", "Shipment Track Summary"),
        )
        current_status = self._extract_field(
            compact,
            "Current Status",
            ("Delivered On:", "Received by:", "Dear Customer", "Track History", "Company Information"),
        )
        origin = self._extract_field(
            compact,
            "Origin",
            ("Destination:", "Booking Date:", "Shipment Track Summary", "Current Status"),
        )
        destination = self._extract_field(
            compact,
            "Destination",
            ("Booking Date:", "Shipment Track Summary", "Current Status"),
        )
        booking_date = self._extract_field(
            compact,
            "Booking Date",
            ("Shipment Track Summary", "Current Status", "Delivered On:"),
        )
        delivered_on = self._extract_field(
            compact,
            "Delivered On",
            ("Received by:", "Track History", "Company Information"),
        )
        received_by = self._extract_field(
            compact,
            "Received by",
            ("No Data Found/Invalid CN", "Track History", "Company Information"),
        )
        customer_message = self._extract_field(
            compact,
            "Dear Customer",
            ("Track History", "Company Information", "About Us"),
        )

        if not current_status:
            for fallback in ("returned to sender", "delivered", "out for delivery", "in transit", "booked"):
                if fallback in html_lower:
                    current_status = fallback.title()
                    break

        events = self._extract_history_events(compact)
        if current_status and not events:
            events.append(
                TrackingEvent(
                    status=current_status,
                    location=destination,
                    timestamp=delivered_on or booking_date,
                    details=f"Received by {received_by}" if received_by else None,
                )
            )

        if not events and not current_status:
            return None

        return TrackingResult(
            courier=self.name,
            trackingNumber=tracking_number,
            success=True,
            status=current_status or events[0].status,
            location=destination,
            timestamp=delivered_on or booking_date or events[0].timestamp,
            events=events,
            error=None,
            strategy="rendered-html",
            shipmentDetails=ShipmentDetails(
                agentReferenceNumber=agent_reference,
                origin=origin,
                destination=destination,
                bookingDate=booking_date,
            ),
            customerMessage=customer_message,
        )

    def _extract_field(self, text: str, label: str, stop_tokens: tuple[str, ...]) -> str | None:
        start = re.search(rf"{re.escape(label)}\s*:\s*", text, re.IGNORECASE)
        if not start:
            return None

        remainder = text[start.end():]
        end_positions = [remainder.find(token) for token in stop_tokens if remainder.find(token) >= 0]
        value = remainder[: min(end_positions)] if end_positions else remainder
        value = " ".join(value.split()).strip(" :")
        return value or None

    def _extract_history_events(self, text: str) -> list[TrackingEvent]:
        history_match = re.search(
            r"Track History\s+Date Time Status\s+(.+?)(?:\s+Company Information|\s+About Us|$)",
            text,
            re.IGNORECASE,
        )
        if not history_match:
            return []

        history_text = history_match.group(1).strip()
        date_pattern = re.compile(
            r"([A-Za-z]{3,9}\s+[A-Za-z]{3}\s+\d{2},\s+\d{4}\s+\d{2}:\d{2})\s+(.+?)(?=(?:[A-Za-z]{3,9}\s+[A-Za-z]{3}\s+\d{2},\s+\d{4}\s+\d{2}:\d{2})|$)"
        )

        events: list[TrackingEvent] = []
        for match in date_pattern.finditer(history_text):
            timestamp = match.group(1).strip()
            raw_status = " ".join(match.group(2).split()).strip()
            details = None
            status = raw_status

            if raw_status.lower().startswith("shipment delivered"):
                status = "Shipment Delivered"
                remainder = raw_status[len("Shipment Delivered"):].strip()
                details = remainder or None
            elif raw_status.lower().startswith("out for delivery"):
                status = "Out For Delivery"
                remainder = raw_status[len("Out For Delivery"):].strip()
                details = remainder or None

            events.append(
                TrackingEvent(
                    status=status,
                    location=None,
                    timestamp=timestamp,
                    details=details,
                )
            )

        return events
