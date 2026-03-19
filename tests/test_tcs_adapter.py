from app.adapters.couriers.tcs import TCSAdapter


def test_tcs_detect_accepts_12_and_13_digits():
    adapter = TCSAdapter(enabled=True)
    assert adapter.detect("123456789012")
    assert adapter.detect("1234567890123")
    assert not adapter.detect("ABC123")


def test_tcs_prefers_api_with_light_fallback():
    adapter = TCSAdapter(enabled=True)
    assert adapter.strategy_priority == ["api", "light-fallback", "rendered-html"]
    assert not hasattr(adapter, "_parse_html")


def test_tcs_api_parser_extracts_official_fields():
    adapter = TCSAdapter(enabled=True)
    payload = {
        "isSuccess": True,
        "responseData": {
            "shipmentinfo": [
                {
                    "consignmentno": "807052578514",
                    "bookingdate": "Mar 17, 2026",
                    "shipper": "904984513",
                    "origin": "ISLAMABAD",
                    "destination": "RAWALPINDI",
                    "referenceno": "904984513",
                }
            ],
            "deliveryinfo": [
                {
                    "station": "RAWALPINDI",
                    "datetime": "Wednesday Mar 18, 2026 10:59",
                    "recievedby": None,
                    "status": "Consignee Moved",
                }
            ],
            "checkpoints": [
                {
                    "datetime": "Wednesday Mar 18, 2026 10:59",
                    "recievedby": None,
                    "status": "Consignee Moved (For Additional Info Contact Local TCS Office)",
                },
                {
                    "datetime": "Wednesday Mar 18, 2026 10:44",
                    "recievedby": "RAWALPINDI",
                    "status": "Arrived at TCS Facility",
                },
            ],
            "shipmentsummary": "Dear Customer\nDelivery attempted on the address but remains undelivered due to CONSIGNEE SHIFT.",
        },
    }

    result = adapter._parse_api_response("807052578514", payload)
    assert result.success is True
    assert result.status == "Consignee Moved"
    assert result.location == "RAWALPINDI"
    assert result.strategy == "api"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "ISLAMABAD"
    assert result.shipmentDetails.destination == "RAWALPINDI"
    assert result.customerMessage is not None
    assert len(result.events) == 2


def test_tcs_api_parser_handles_invalid_consignment():
    adapter = TCSAdapter(enabled=True)
    payload = {
        "isSuccess": True,
        "responseData": {
            "shipmentinfo": None,
            "deliveryinfo": None,
            "checkpoints": [],
            "shipmentsummary": "No Data Found/Invalid CN",
        },
    }

    result = adapter._parse_api_response("000000000000", payload)
    assert result.success is False
    assert result.error == "Tracking number not found in TCS system."
    assert result.strategy == "api"
