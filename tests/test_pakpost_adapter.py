from app.adapters.couriers.pakpost import PakistanPostAdapter


def test_pakpost_detect_uses_known_prefixes():
    adapter = PakistanPostAdapter(enabled=True)
    assert adapter.detect("UMS123456789")
    assert adapter.detect("ems123456789".upper())
    assert not adapter.detect("1234567890")


def test_pakpost_history_parser_deduplicates_rows_and_keeps_source_order():
    adapter = PakistanPostAdapter(enabled=True)
    html = """
    <html><body>
      <span id="LblDeliveryOffice">Kohat GPO</span>
      <div id="TrackDetailDiv">
        <table>
          <tr><td colspan="4"><div>July 17, 2025</div></td></tr>
          <tr><td></td><td>9:56 AM</td><td><b>Kohat GPO</b></td><td>Delivered at delivery office <b>Kohat GPO</b> to <b>ADDRESSEE</b></td></tr>
          <tr><td colspan="4"><div>July 16, 2025</div></td></tr>
          <tr><td></td><td>9:58 AM</td><td><b>Kohat GPO</b></td><td>Sent out for delivery</td></tr>
          <tr><td></td><td>9:58 AM</td><td><b>Kohat GPO</b></td><td>Sent out for delivery</td></tr>
        </table>
      </div>
    </body></html>
    """

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    history = adapter._extract_history(soup)

    assert len(history) == 2
    assert history[0].status == "Delivered at delivery office Kohat GPO to ADDRESSEE"
    assert history[0].timestamp == "July 17, 2025 9:56 AM"
    assert history[1].status == "Sent out for delivery"


def test_pakpost_result_includes_booking_and_delivery_office():
    adapter = PakistanPostAdapter(enabled=True)
    html = """
    <html><body>
      <span id="LblBookingOffice">Rawalpindi GPO</span>
      <span id="LblDeliveryOffice">Abbottabad DMO</span>
      <div id="TrackDetailDiv">
        <table>
          <tr><td colspan="4"><div>March 17, 2026</div></td></tr>
          <tr><td></td><td>8:43 AM</td><td><b>Abbottabad</b></td><td>Dispatch from DMO Abbottabad to delivery office Rajoya</td></tr>
        </table>
      </div>
    </body></html>
    """

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    history = adapter._extract_history(soup)

    result = adapter._parse_result("RGL169532333", soup, history)

    assert result.shipmentDetails is not None
    assert result.shipmentDetails.origin == "Rawalpindi GPO"
    assert result.shipmentDetails.destination == "Abbottabad DMO"
