import pytest
from unittest.mock import AsyncMock, patch

from smartx_rfid.devices.generic.SERIAL._main import SERIAL


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

    def test_data_received(self):
        """Test data_received method with simple message"""
        serial_device = SERIAL()

        # Mock asyncio.create_task to prevent actual async execution
        with patch("asyncio.create_task") as mock_create_task:
            # Mock the on_event to be an AsyncMock
            serial_device.on_event = AsyncMock()

            # Test with complete message
            test_data = b"test message\n"
            serial_device.data_received(test_data)

            # Buffer should be empty after processing complete message
            assert len(serial_device.rx_buffer) == 0

            # Verify that create_task was called (for on_event and timeout)
            assert mock_create_task.called


if __name__ == "__main__":
    pytest.main([__file__])
