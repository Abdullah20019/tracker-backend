from app.adapters.couriers.mp import MPAdapter


def test_mp_parser_extracts_details_and_timeline():
    adapter = MPAdapter(enabled=True)
    html = """
    <div class="tracking-row">
      <div class="col">
        <label class="form-label">Consignment Number</label>
        <input type="text" class="form-control" value="151010784112" readonly>
      </div>
      <div class="col">
        <label class="form-label">Order ID</label>
        <input type="text" class="form-control" value="Web Order 54038" readonly>
      </div>
      <div class="col">
        <label class="form-label">Booking Date</label>
        <input type="text" class="form-control" value="19 Jun 2025" readonly>
      </div>
      <div class="col">
        <label class="form-label">From</label>
        <input type="text" class="form-control" value="Book Villa ( Cod )" readonly>
        <input type="text" class="form-control mt-2" value="Islamabad" readonly>
      </div>
      <div class="col">
        <label class="form-label">To</label>
        <input type="text" class="form-control" value="Asim Ali" readonly>
        <input type="text" class="form-control mt-2" value="Jhelum" readonly>
      </div>
    </div>
    <div class="order-track-step last">
      <div class="order-track-text order-track-text-left">
        <span class="order-track-text-sub last-date">30 May 2025<br>03:50 pm</span>
      </div>
      <div class="order-track-text order-track-text-right">
        <p class="order-track-text-stat status">Delivered</p>
        <p class="order-track-text-stat location">JEHLUM</p>
        <p class="order-track-text-stat status-message">The shipment has been delivered.</p>
      </div>
    </div>
    <div class="order-track-step">
      <div class="order-track-text order-track-text-left">
        <span class="order-track-text-sub">30 May 2025<br>08:00 am</span>
      </div>
      <div class="order-track-text order-track-text-right">
        <p class="order-track-text-stat status">Out-for-Delivery</p>
        <p class="order-track-text-stat location">JEHLUM</p>
        <p class="order-track-text-stat status-message">The shipment has been scheduled for delivery.</p>
      </div>
    </div>
    """

    result = adapter._parse_html("151010784112", html)

    assert result.success is True
    assert result.trackingNumber == "151010784112"
    assert result.status == "Delivered"
    assert result.location == "JEHLUM"
    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "Islamabad"
    assert result.shipmentDetails.destination == "Jhelum"
    assert len(result.events) == 2
    assert result.progressSteps
    assert result.progressSteps[-1].label == "Delivered"
    assert result.progressSteps[-1].active is True
