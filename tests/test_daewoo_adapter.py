from app.adapters.couriers.daewoo import DaewooAdapter


def test_daewoo_parser_handles_45_day_limit():
    adapter = DaewooAdapter(enabled=True)

    result = adapter._parse_payload("3004961775", {"StatusCode": 400, "Title": "Tracking available for bookings within 45 days"})

    assert result.success is False
    assert result.error == "Tracking available for bookings within 45 days"


def test_daewoo_parser_extracts_history():
    adapter = DaewooAdapter(enabled=True)
    payload = {
        "StatusCode": 200,
        "BookingDetails": {
            "booking_id": "26735809",
            "consignmentNo": None,
            "track_code": 9378,
            "booking_datetime": "2026-03-10T09:15:00",
            "stn": "RAWALPINDI",
            "sccpn": "MAIN",
            "dtn": "LAHORE",
            "dccpn": "AGT SUNDER INDUSTRIAL",
            "customer_group_name": "FASTEX - HOME DELIVERY",
            "tpieces": 1,
            "senderDetails": [
                {
                    "person": "THE BKRY NONCOD (HD)",
                    "phoneNo": "03061112253",
                    "address": "18-A MAIN KAGHAN ROAD",
                }
            ],
            "receiverDetail": [
                {
                    "name": "MR FAISAL",
                    "phoneNo": "03425956699",
                    "address": "TEHZEEB BAKERS",
                }
            ],
            "orderinformation": [
                {
                    "sType": "FASTEX - HOME DELIVERY",
                }
            ],
            "hdTrackingDetail": [
                {
                    "barCode": "6308194610",
                    "dateTime": "2026-02-17T20:06:00",
                    "status": "DL - DELIVERED - DELIVERED",
                    "reason": "ON ROUTE",
                    "source": "LAHORE - AGT SUNDER INDUSTRIAL",
                },
                {
                    "barCode": "6308194610",
                    "dateTime": "2026-02-17T08:10:00",
                    "status": "OR - ON ROUTE - ON ROUTE",
                    "reason": "ON ROUTE",
                    "source": "RAWALPINDI - MAIN",
                },
            ],
        },
    }

    result = adapter._parse_payload("6308194610", payload)

    assert result.success is True
    assert result.status == "DL - DELIVERED"
    assert result.location == "LAHORE - AGT SUNDER INDUSTRIAL"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.agentReferenceNumber == "26735809"
    assert result.shipmentDetails.trackingCode == "9378"
    assert result.shipmentDetails.origin == "RAWALPINDI - MAIN"
    assert result.shipmentDetails.destination == "LAHORE - AGT SUNDER INDUSTRIAL"
    assert result.shipmentDetails.shipper == "THE BKRY NONCOD (HD)"
    assert result.shipmentDetails.consignee == "MR FAISAL"
    assert result.shipmentDetails.deliveryType == "FASTEX - HOME DELIVERY"
    assert result.shipmentDetails.senderAddress == "18-A MAIN KAGHAN ROAD"
    assert result.shipmentDetails.receiverAddress == "TEHZEEB BAKERS"
    assert result.progressSteps[-1].label == "Delivered"
    assert result.progressSteps[-1].active is True
