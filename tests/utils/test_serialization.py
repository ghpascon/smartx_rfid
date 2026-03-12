import pytest
from smartx_rfid.webhook import WebhookManager
from datetime import datetime, date
from decimal import Decimal


class CustomClass:
    """Mock class for testing custom object serialization"""

    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value


class TestSerialization:
    @pytest.fixture
    def webhook_manager(self):
        """Fixture to create a WebhookManager instance for tests"""
        return WebhookManager(url="http://example.com/webhook")

    def test_serialize_none(self, webhook_manager):
        """Test that None remains None"""
        result = webhook_manager._make_serializable(None)
        assert result is None

    def test_serialize_datetime(self, webhook_manager):
        """Test datetime serialization to ISO format"""
        dt = datetime(2024, 1, 17, 10, 30, 45)
        result = webhook_manager._make_serializable(dt)
        assert isinstance(result, str)
        assert result == "2024-01-17T10:30:45"

    def test_serialize_date(self, webhook_manager):
        """Test date serialization to ISO format"""
        d = date(2024, 1, 17)
        result = webhook_manager._make_serializable(d)
        assert isinstance(result, str)
        assert result == "2024-01-17"

    def test_serialize_decimal(self, webhook_manager):
        """Test Decimal conversion to float"""
        decimal_value = Decimal("123.456")
        result = webhook_manager._make_serializable(decimal_value)
        assert isinstance(result, float)
        assert result == 123.456

    def test_serialize_bytes(self, webhook_manager):
        """Test bytes conversion to string"""
        byte_data = b"Hello World"
        result = webhook_manager._make_serializable(byte_data)
        assert isinstance(result, str)
        assert result == "Hello World"

    def test_serialize_bytes_invalid_utf8(self, webhook_manager):
        """Test bytes that cannot be decoded as UTF-8"""
        byte_data = b"\x80\x81\x82"
        result = webhook_manager._make_serializable(byte_data)
        assert isinstance(result, str)

    def test_serialize_set(self, webhook_manager):
        """Test set conversion to list"""
        set_data = {1, 2, 3, 4, 5}
        result = webhook_manager._make_serializable(set_data)
        assert isinstance(result, list)
        assert len(result) == 5
        assert set(result) == set_data

    def test_serialize_primitive_types(self, webhook_manager):
        """Test that primitive types remain unchanged"""
        assert webhook_manager._make_serializable("string") == "string"
        assert webhook_manager._make_serializable(42) == 42
        assert webhook_manager._make_serializable(3.14) == 3.14
        assert webhook_manager._make_serializable(True) is True
        assert webhook_manager._make_serializable(False) is False

    def test_serialize_list(self, webhook_manager):
        """Test list serialization (recursive)"""
        list_data = [1, "string", datetime(2024, 1, 17), {"key": "value"}]
        result = webhook_manager._make_serializable(list_data)
        assert isinstance(result, list)
        assert result[0] == 1
        assert result[1] == "string"
        assert result[2] == "2024-01-17T00:00:00"
        assert result[3] == {"key": "value"}

    def test_serialize_tuple(self, webhook_manager):
        """Test tuple serialization to list (recursive)"""
        tuple_data = (1, 2, datetime(2024, 1, 17))
        result = webhook_manager._make_serializable(tuple_data)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[2] == "2024-01-17T00:00:00"

    def test_serialize_dict(self, webhook_manager):
        """Test dictionary serialization (recursive)"""
        dict_data = {
            "name": "test",
            "timestamp": datetime(2024, 1, 17, 10, 30),
            "count": 42,
            "nested": {"inner": datetime(2024, 1, 17)},
        }
        result = webhook_manager._make_serializable(dict_data)
        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["timestamp"] == "2024-01-17T10:30:00"
        assert result["count"] == 42
        assert result["nested"]["inner"] == "2024-01-17T00:00:00"

    def test_serialize_custom_class(self, webhook_manager):
        """Test custom class serialization using __dict__"""
        custom_obj = CustomClass(name="test_object", value=100)
        result = webhook_manager._make_serializable(custom_obj)
        assert isinstance(result, dict)
        assert result["name"] == "test_object"
        assert result["value"] == 100

    def test_serialize_nested_custom_class(self, webhook_manager):
        """Test nested custom class with datetime attributes"""

        class NestedClass:
            def __init__(self):
                self.timestamp = datetime(2024, 1, 17, 15, 30)
                self.data = CustomClass("nested", 50)

        nested_obj = NestedClass()
        result = webhook_manager._make_serializable(nested_obj)
        assert isinstance(result, dict)
        assert result["timestamp"] == "2024-01-17T15:30:00"
        assert result["data"]["name"] == "nested"
        assert result["data"]["value"] == 50

    def test_serialize_complex_structure(self, webhook_manager):
        """Test complex nested structure with multiple types"""
        complex_data = {
            "device": "reader_01",
            "tags": [
                {
                    "epc": "1234567890",
                    "timestamp": datetime(2024, 1, 17, 10, 30, 45),
                    "rssi": Decimal("-45.5"),
                },
                {
                    "epc": "0987654321",
                    "timestamp": datetime(2024, 1, 17, 10, 30, 46),
                    "rssi": Decimal("-50.2"),
                },
            ],
            "reader_info": CustomClass("R700", 1),
            "active_antennas": {1, 2, 3, 4},
            "metadata": b"binary_data",
        }

        result = webhook_manager._make_serializable(complex_data)

        assert result["device"] == "reader_01"
        assert len(result["tags"]) == 2
        assert result["tags"][0]["timestamp"] == "2024-01-17T10:30:45"
        assert result["tags"][0]["rssi"] == -45.5
        assert result["tags"][1]["rssi"] == -50.2
        assert result["reader_info"]["name"] == "R700"
        assert result["reader_info"]["value"] == 1
        assert isinstance(result["active_antennas"], list)
        assert len(result["active_antennas"]) == 4
        assert result["metadata"] == "binary_data"

    def test_serialize_empty_containers(self, webhook_manager):
        """Test serialization of empty containers"""
        assert webhook_manager._make_serializable([]) == []
        assert webhook_manager._make_serializable({}) == {}
        assert webhook_manager._make_serializable(set()) == []
        assert webhook_manager._make_serializable(()) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
