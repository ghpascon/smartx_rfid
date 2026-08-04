from smartx_rfid.parser import get_serial_from_tid, serialize_gtin
import pytest


class TestParser:
    def test_serial_from_tid(self):
        invalid_format_tid = "E280"
        serial = get_serial_from_tid(invalid_format_tid)
        assert serial is None

        valid_tid = "e280119020006bf18b92032a"
        serial = get_serial_from_tid(valid_tid)
        assert serial == "188736049667"

        ean = "7891234567895"
        sgtin = serialize_gtin(ean, serial)
        assert sgtin == "3035e1a48837756bf18b9203"


if __name__ == "__main__":
    pytest.main([__file__])
