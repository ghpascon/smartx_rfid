import pytest

from smartx_rfid.devices import SERIAL


class TestSERIAL:
    """Simple test suite for SERIAL class"""

    def test_create_object_default(self):
        """Test creating SERIAL object with default parameters"""
        serial_device = SERIAL()

        # Check if object is instance of SERIAL class
        assert isinstance(serial_device, SERIAL)

        # Check basic default attributes
        assert serial_device.port == "AUTO"
        assert serial_device.is_auto is True

    def test_create_object_and_check_instance(self):
        """Test creating SERIAL object and verify it's the correct class"""
        serial_device = SERIAL(
            name="TEST_SERIAL",
            port="COM3",
        )

        # Check if object is instance of SERIAL class
        assert isinstance(serial_device, SERIAL)

        # Check basic default attributes
        assert serial_device.name == "TEST_SERIAL"
        assert serial_device.port == "COM3"
        assert serial_device.is_auto is False


if __name__ == "__main__":
    pytest.main([__file__])
