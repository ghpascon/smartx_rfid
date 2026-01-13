import pytest
from unittest.mock import AsyncMock, Mock, patch

from smartx_rfid.devices import TCP


class TestTCP:
    """Simple test suite for TCP class"""

    def test_create_object_default(self):
        """Test creating TCP object with default parameters"""
        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.generic.TCP._main.on_event", Mock()):
            tcp_device = TCP()

            # Check if object is instance of TCP class
            assert isinstance(tcp_device, TCP)

            # Check basic default attributes
            assert tcp_device.name == "GENERIC_TCP"
            assert tcp_device.ip == "192.168.1.101"
            assert tcp_device.port == 23
            assert tcp_device.is_connected is False

    def test_create_object_and_check_instance(self):
        """Test creating TCP object and verify it's the correct class"""
        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.generic.TCP._main.on_event", Mock()):
            tcp_device = TCP(
                name="TEST_TCP",
                ip="192.168.1.100",
                port=4001,
            )

            # Check if object is instance of TCP class
            assert isinstance(tcp_device, TCP)

            # Check basic attributes
            assert tcp_device.name == "TEST_TCP"
            assert tcp_device.ip == "192.168.1.100"
            assert tcp_device.port == 4001
            assert tcp_device.is_connected is False

    @pytest.mark.asyncio
    async def test_write_method_not_connected(self):
        """Test write method when not connected"""
        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.generic.TCP._main.on_event", Mock()):
            tcp_device = TCP()

            # Mock logging and on_event
            with patch("logging.info"):
                await tcp_device.write("test message")

                # Should not attempt to write when not connected
                assert tcp_device.writer is None

    @pytest.mark.asyncio
    async def test_write_method_connected(self):
        """Test write method when connected"""
        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.generic.TCP._main.on_event", Mock()):
            tcp_device = TCP()

            # Mock writer with regular Mock (not AsyncMock)
            mock_writer = Mock()
            mock_writer.write = Mock()
            mock_writer.drain = AsyncMock()  # drain is async, so it needs AsyncMock

            # Mock on_event to prevent the coroutine warning
            tcp_device.on_event = Mock()

            tcp_device.writer = mock_writer
            tcp_device.is_connected = True

            # Test writing data
            await tcp_device.write("test message")

            # Verify write and drain were called
            mock_writer.write.assert_called_once_with(b"test message\n")
            mock_writer.drain.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
