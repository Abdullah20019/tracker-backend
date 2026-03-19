from app.adapters.couriers.trax import TraxAdapter


def test_trax_parser_extracts_shipment_history():
    adapter = TraxAdapter(enabled=True)
    payload = {
        "shipments": {
            "807052578514": {
                "tracking_number": "807052578514",
                "pickup": {"origin": "Karachi"},
                "shipper": {"name": "Demo Store"},
                "consignee": {"name": "Ali Raza", "destination": "Lahore"},
                "tracking_history": [
                    {
                        "status": "Delivered",
                        "date_time": "2026-03-18 12:45",
                        "location": "Lahore",
                        "details": "Received by customer",
                    },
                    {
                        "status": "Out for delivery",
                        "date_time": "2026-03-18 10:00",
                        "location": "Lahore",
                    },
                ],
            }
        }
    }

    result = adapter._parse_payload("807052578514", payload)

    assert result.success is True
    assert result.status == "Delivered"
    assert result.location == "Lahore"
    assert result.events[0].details == "Received by customer"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "Karachi"
    assert result.shipmentDetails.destination == "Lahore"
    assert result.shipmentDetails.shipper == "Demo Store"
    assert result.shipmentDetails.consignee == "Ali Raza"
    assert result.customerMessage == "Received by customer"
    assert [step.label for step in result.progressSteps] == [
        "Picked Up",
        "In Transit",
        "At Destination",
        "Out for Delivery",
        "Delivered",
    ]
    assert result.progressSteps[-1].active is True
    assert result.strategy == "api"


def test_trax_parser_handles_invalid_numbers():
    adapter = TraxAdapter(enabled=True)

    result = adapter._parse_payload("000000", {"invalid": ["000000"]})

    assert result.success is False
    assert result.error == "Tracking number not found in Trax system."
