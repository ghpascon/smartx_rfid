from smartx_rfid.parser import get_serial_from_tid, serialize_gtin
from smartx_rfid.parser.main import deserialize_split, serialize_split
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

    @pytest.mark.parametrize(
        ("product_code", "serial", "product_code_length", "expected"),
        [
            ("12345", "678", 12, "000000012345000000000678"),
            ("12345678", "123456", 8, "123456780000000000123456"),
        ],
    )
    def test_serialize_split(self, product_code, serial, product_code_length, expected):
        assert serialize_split(product_code, serial, product_code_length) == expected

    def test_serialize_split_rejects_product_code_longer_than_limit(self):
        with pytest.raises(ValueError, match="Product code length exceeds"):
            serialize_split("1234567890123", "1")

    def test_serialize_split_rejects_combined_length_over_24(self):
        with pytest.raises(ValueError, match="Combined length"):
            serialize_split("123456789012", "1234567890123")

    @pytest.mark.parametrize(
        ("serialized", "product_code_length", "expected"),
        [
            ("000000012345000000000678", 12, ("12345", "678")),
            ("123456780000000000123456", 8, ("12345678", "123456")),
            ("000000000000000000000000", 12, ("", "")),
        ],
    )
    def test_deserialize_split(self, serialized, product_code_length, expected):
        assert deserialize_split(serialized, product_code_length) == expected

    @pytest.mark.parametrize("serialized", ["123", "0" * 25])
    def test_deserialize_split_rejects_length_other_than_24(self, serialized):
        with pytest.raises(ValueError, match="exactly 24 hexadecimal characters"):
            deserialize_split(serialized)


if __name__ == "__main__":
    pytest.main([__file__])
