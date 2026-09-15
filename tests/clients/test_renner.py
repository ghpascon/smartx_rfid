from smartx_rfid.clients.renner import get_renner_sku
import pytest


class TestRennerSku:
    def test_get_sku_from_epc(self):
        epc = "3074257bf7194e4000001a85"
        sku = get_renner_sku(epc)
        assert sku == "41214356835904"

        invalid_epc = "INVALID_EPC_123456"
        sku_invalid = get_renner_sku(invalid_epc)
        assert sku_invalid is None


if __name__ == "__main__":
    pytest.main([__file__])
