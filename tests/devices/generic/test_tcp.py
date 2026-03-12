import pytest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    pytest.main([__file__])
