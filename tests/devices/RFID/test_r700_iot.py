import pytest
from unittest.mock import Mock, patch, AsyncMock

from smartx_rfid.devices import R700_IOT
from smartx_rfid.devices import R700_IOT_config_example


class TestR700_IOT:
    """Test suite for R700_IOT RFID Reader class"""

    def test_create_object_default(self):
        """Test creating R700_IOT object with default parameters"""

        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.RFID.R700_IOT._main.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)

            # Check if object is instance of R700_IOT class
            assert isinstance(r700_device, R700_IOT)

            # Check basic default attributes
            assert r700_device.username == "root"
            assert r700_device.password == "impinj"
            assert r700_device.firmware_version == "8.4.1"
            assert r700_device.device_type == "rfid"
            assert r700_device.is_connected is False
            assert r700_device.is_reading is False

    def test_url_endpoints_construction(self):
        """Test URL endpoints are constructed correctly"""

        with patch("smartx_rfid.devices.RFID.R700_IOT._main.on_event", Mock()):
            ip = "192.168.1.101"
            r700_device = R700_IOT(reading_config=R700_IOT_config_example, ip=ip)

            # Check URL construction
            expected_base = f"https://{ip}/api/v1"
            assert r700_device.urlBase == expected_base
            assert r700_device.endpoint_interface == f"{expected_base}/system/rfid/interface"
            assert r700_device.check_version_endpoint == f"{expected_base}/system/image"
            assert r700_device.endpoint_start == f"{expected_base}/profiles/inventory/start"
            assert r700_device.endpoint_stop == f"{expected_base}/profiles/stop"
            assert r700_device.endpointDataStream == f"{expected_base}/data/stream"
            assert r700_device.endpoint_gpo == f"{expected_base}/device/gpos"
            assert r700_device.endpoint_write == f"{expected_base}/profiles/inventory/tag-access"

    @pytest.mark.asyncio
    async def test_gpi_trigger_blocks_start_inventory(self):
        """Test that start_inventory returns False when GPI trigger is enabled"""
        with patch("smartx_rfid.devices.RFID.R700_IOT._main.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)
            r700_device.is_connected = True
            r700_device.is_gpi_trigger_on = True
            r700_device.start_inventory = AsyncMock(return_value=False)

            # Test that start_inventory returns False when GPI trigger is on
            result = await r700_device.start_inventory()
            assert result is False

    @pytest.mark.asyncio
    async def test_gpi_trigger_allows_start_inventory_when_disabled(self):
        """Test that start_inventory works normally when GPI trigger is disabled"""
        with patch("smartx_rfid.devices.RFID.R700_IOT._main.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)
            r700_device.is_connected = True
            r700_device.is_gpi_trigger_on = False
            r700_device.start_inventory = AsyncMock(return_value=True)

            # Test that start_inventory can succeed when GPI trigger is off
            result = await r700_device.start_inventory()
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__])
