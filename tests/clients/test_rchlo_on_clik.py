from smartx_rfid.clients.on_click import OnClickClient
import pytest


class TestOnClickClient:
    def test_serialize_deserialize_tag(self):
        product_code = 123456
        tid = "e2801190200070a18b9f032a"
        serialized = OnClickClient.serialize_tag(product_code, tid)
        assert serialized == "000000123456208868712195"
        deserialized = OnClickClient.deserialize_tag(serialized)
        assert deserialized["product_code"] == product_code
        assert deserialized["serial"] == 208868712195


if __name__ == "__main__":
    pytest.main([__file__])
