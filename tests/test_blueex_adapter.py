from app.adapters.couriers.blueex import BlueExAdapter


def test_blueex_parser_extracts_progress_steps():
    adapter = BlueExAdapter(enabled=True)
    html = """
    <div class='trackingInformation bg-base mb-4' id='blueEx_5000000001'>
      <span class='sngltrackno text-center d-block'>5000000001</span>
      <div class='trackingResult my-3'>
        <ul class='clearfix text-center'>
          <li class='booked'><p>Booked</p></li>
          <li class='recevied'><p>Received at BlueEx</p></li>
          <li class='intransit'><p>In Transit</p></li>
          <li class='delivery'><p>Out For Delivery</p></li>
          <li class='delivered'><p>Delivered</p></li>
        </ul>
      </div>
      <div class='trackinfoInner'>
        <p class='blue d-inline-block'>BlueEX Shipping Label : 5000000001 (4.15 Seconds)</p>
        <p>Aug 25th, 2025(12:18 PM) - Order information received, pending at Shipper's end.</p>
        <p>Aug 25th, 2025(10:28 PM) - Shipment is on route to Islamabad</p>
        <p>Aug 25th, 2025(10:34 PM) - Shipment reached blueEX Karachi Warehouse, Karachi</p>
        <p>Aug 28th, 2025(09:27 AM) - Shipment has reached blueEX Islamabad - Islamabad</p>
        <p>Aug 28th, 2025(02:49 PM) - Out For Delivery</p>
        <p>Aug 28th, 2025(02:50 PM) - Delivered to Customer</p>
      </div>
    </div>
    """

    result = adapter._parse_html("5000000001", html)

    assert result.success is True
    assert result.trackingNumber == "5000000001"
    assert result.status == "Delivered to Customer"
    assert result.timestamp == "Aug 28th, 2025(02:50 PM)"
    assert result.location == "Islamabad"
    assert [event.status for event in result.events] == [
        "Order information received, pending at Shipper's end.",
        "Shipment is on route to Islamabad",
        "Shipment reached blueEX Karachi Warehouse",
        "Shipment has reached blueEX Islamabad",
        "Out For Delivery",
        "Delivered to Customer",
    ]
    assert len(result.progressSteps) == 5
    assert [step.label for step in result.progressSteps] == [
        "Booked",
        "Received at BlueEx",
        "In Transit",
        "Out For Delivery",
        "Delivered",
    ]
    assert result.customerMessage is not None
