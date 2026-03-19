from app.adapters.couriers.postex import PostExAdapter


def test_postex_parser_extracts_status_history():
    adapter = PostExAdapter(enabled=True)
    payload = {
        "statusCode": "200",
        "statusMessage": "Successfully Operated",
        "dist": {
            "customerName": "Rizwan Younas",
            "trackingNumber": "29195910010119",
            "orderPickupDate": "2026-01-24T19:35:16.000+0500",
            "transactionStatusHistory": [
                {
                    "transactionStatusMessage": "Delivered to Customer",
                    "transactionStatusMessageCode": "0005",
                    "modifiedDatetime": "2026-01-27T17:31:55.000+0500",
                },
                {
                    "transactionStatusMessage": "Enroute for Delivery",
                    "transactionStatusMessageCode": "0004",
                    "modifiedDatetime": "2026-01-27T10:04:16.000+0500",
                },
                {
                    "transactionStatusMessage": "Arrived at Transit Hub SGR",
                    "transactionStatusMessageCode": "0035",
                    "modifiedDatetime": "2026-01-27T08:22:17.000+0500",
                },
                {
                    "transactionStatusMessage": "At TWO BROTHERS MENS WEAR Warehouse",
                    "transactionStatusMessageCode": "0001",
                    "modifiedDatetime": "2026-01-22T22:47:27.000+0500",
                },
            ],
        },
    }

    result = adapter._parse_payload("29195910010119", payload)

    assert result.success is True
    assert result.status == "Delivered to Customer"
    assert result.location == "SGR"
    assert result.timestamp == "27 Jan 2026 05:31 PM"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.consignee == "Rizwan Younas"
    assert result.shipmentDetails.bookingDate == "24 Jan 2026 07:35 PM"
    assert result.progressSteps[-1].label == "Delivered"
    assert result.progressSteps[-1].active is True


def test_postex_parser_handles_missing_distribution():
    adapter = PostExAdapter(enabled=True)

    result = adapter._parse_payload("00000000000000", {"statusCode": "200", "statusMessage": "Successfully Operated"})

    assert result.success is False
    assert result.error == "Tracking number not found in PostEx system."
