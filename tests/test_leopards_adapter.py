from app.adapters.couriers.leopards import LeopardsAdapter


def test_leopards_parser_handles_not_found_message():
    adapter = LeopardsAdapter(enabled=True)
    html = """
    <html><body>
      <div>Your query about "KI8552676556" appeared to be invalid / record not found.</div>
      <div>Please enter a valid / correct consignment number.</div>
    </body></html>
    """

    result = adapter._parse_html("KI8552676556", html)

    assert result.success is False
    assert result.error == "Tracking number not found in Leopards system."


def test_leopards_parser_extracts_tracking_items():
    adapter = LeopardsAdapter(enabled=True)
    html = """
    <div id="bar-progress">
      <div class="step"><span class="number-container"><span class="number">1</span></span>Shipment picked</div>
      <div class="step step-active"><span class="number-container"><span class="number">2</span></span>Out for Delivery</div>
    </div>
    <table class="table table-striped table-bordered">
      <tr><th colspan="4">Return To Sender</th></tr>
      <tr>
        <td><b>Signed for by :</b></td>
        <td>ALI - SELF</td>
        <td><b>Dated:</b></td>
        <td><p>12 March 2026, 15:06</p></td>
      </tr>
    </table>
    <table class="table table-striped table-bordered">
      <tr><td colspan="4">Shipment Detail</td></tr>
      <tr>
        <td><b>Origin :</b></td>
        <td>KASUR</td>
        <td><b>Destination :</b></td>
        <td>KARACHI</td>
      </tr>
      <tr>
        <td><b>Reference No. :</b></td>
        <td>6255893</td>
        <td><b>Booking Date :</b></td>
        <td>12 March 2026, 15:06</td>
      </tr>
      <tr>
        <td><b>Pieces :</b></td>
        <td>3</td>
        <td><b>Consignee :</b></td>
        <td>MUHAMMAD SAJID KHAN</td>
      </tr>
    </table>
    <div class="tracking-item">
      <div class="tracking-date">18 Mar 2026 <span>10:00</span></div>
      <div class="tracking-content">Out for Delivery <span>Lahore</span></div>
    </div>
    <div class="tracking-item">
      <div class="tracking-date">18 Mar 2026 <span>07:30</span></div>
      <div class="tracking-content">Shipment Received <span>Lahore</span></div>
    </div>
    """

    result = adapter._parse_html("KI8552676556", html)

    assert result.success is True
    assert result.status == "Out for Delivery"
    assert result.location == "KARACHI"
    assert result.timestamp == "12 March 2026, 15:06"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "KASUR"
    assert result.shipmentDetails.destination == "KARACHI"
    assert result.shipmentDetails.pieces == "3"
    assert result.shipmentDetails.signedForBy == "ALI - SELF"
    assert len(result.progressSteps) == 2
    assert len(result.events) == 2


def test_leopards_parser_falls_back_to_route_details_from_timeline():
    adapter = LeopardsAdapter(enabled=True)
    html = """
    <div id="bar-progress">
      <div class="step"><span class="number-container"><span class="number">1</span></span>Shipment picked</div>
      <div class="step"><span class="number-container"><span class="number">2</span></span>Dispatched</div>
      <div class="step step-active"><span class="number-container"><span class="number">3</span></span>Delivered</div>
    </div>
    <table class="table table-striped table-bordered">
      <tr><th colspan="4">Delivered</th></tr>
      <tr>
        <td><b>Signed for by :</b></td>
        <td>M ABBAS - STAFF</td>
        <td><b>Dated:</b></td>
        <td><p>26 December 2025, 20:41</p></td>
      </tr>
    </table>
    <div class="tracking-item">
      <div class="tracking-date">26 December, 2025 <span>(20:41)</span></div>
      <div class="tracking-content">Delivered at KARACHI M ABBAS ~ STAFF</div>
    </div>
    <div class="tracking-item">
      <div class="tracking-date">22 December, 2025 <span>(22:37)</span></div>
      <div class="tracking-content">Shipment Dispatched from LAHORE to KARACHI</div>
    </div>
    <div class="tracking-item">
      <div class="tracking-date">22 December, 2025 <span>(22:33)</span></div>
      <div class="tracking-content">Shipment Picked at ORIGIN LAHORE</div>
    </div>
    """

    result = adapter._parse_html("LE0580187470", html)

    assert result.success is True
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "LAHORE"
    assert result.shipmentDetails.destination == "KARACHI"
