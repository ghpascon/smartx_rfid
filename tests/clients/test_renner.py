from smartx_rfid.clients.renner import (
    get_renner_sku,
    renner_get_epc_from_sku,
    renner_get_address_by_epc,
    renner_serialize_epc_by_address,
)
from smartx_rfid.utils.regex import regex_hex
import pytest


class TestRennerSku:
    def test_get_sku_from_epc(self):
        epc = "3074257bf7194e4000001a85"
        sku = get_renner_sku(epc)
        assert sku == "41214356835904"

        invalid_epc = "INVALID_EPC_123456"
        sku_invalid = get_renner_sku(invalid_epc)
        assert sku_invalid is None

    def test_get_epc_from_sku_with_serial(self):
        epc = renner_get_epc_from_sku("41214356835904", serial=0x1A85)

        assert epc == "0000257bf7194e4000001a85"
        assert len(epc) == 24
        assert get_renner_sku(epc) == "41214356835904"


class TestRennerAddress:
    def test_serialize_and_decode_address(self):
        address = "EN0.C131.S002.N1.0"
        epc = renner_serialize_epc_by_address(address)

        assert epc == "edc000000131000200010000"
        assert regex_hex(epc, 24)
        assert renner_get_address_by_epc(epc) == address

    def test_get_address_rejects_non_hex_epc(self):
        with pytest.raises(ValueError, match="Invalid EPC format"):
            renner_get_address_by_epc("edc00000013100020001000g")

    def test_get_address_rejects_epc_with_wrong_length(self):
        with pytest.raises(ValueError, match="Invalid EPC format"):
            renner_get_address_by_epc("edc00000013100020001000")

    def test_serialize_address_rejects_wrong_number_of_parts(self):
        with pytest.raises(ValueError, match="Invalid address format"):
            renner_serialize_epc_by_address("EN0.C131.S002.N1")


if __name__ == "__main__":
    pytest.main([__file__])
