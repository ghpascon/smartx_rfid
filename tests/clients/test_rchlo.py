from smartx_rfid.clients.rchlo import rchlo_get_sku_from_epc
import pytest


class TestRCHLO:
    def test_get_sku_from_epc(self):
        epc = "3074257bf7194e4000001a85"
        sku = rchlo_get_sku_from_epc(epc)
        assert sku == "4257bf7194e"

        invalid_epc = "INVALID_EPC_123456"
        sku_invalid = rchlo_get_sku_from_epc(invalid_epc)
        assert sku_invalid is None


if __name__ == "__main__":
    pytest.main([__file__])
