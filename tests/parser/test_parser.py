from smartx_rfid.parser import get_serial_from_tid
import pytest
from pyepc import SGTIN


class TestParser:
    def test_serial_from_tid(self):
        invalid_format_tid = "E280"
        serial = get_serial_from_tid(invalid_format_tid)
        assert serial is None

        valid_tid = "e280119020006bf18b92032a"
        serial = get_serial_from_tid(valid_tid)
        assert serial == "188736049667"

        ean = "7891234567895"
        sgtin = SGTIN.from_sgtin(ean.zfill(14), serial, 7)
        sgtin = sgtin.encode().lower()
        assert sgtin == "3035e1a48837756bf18b9203"


if __name__ == "__main__":
    pytest.main([__file__])
