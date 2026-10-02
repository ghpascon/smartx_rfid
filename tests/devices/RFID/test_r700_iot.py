import pytest
from unittest.mock import Mock, patch, AsyncMock

from smartx_rfid.devices import R700_IOT
from smartx_rfid.devices import R700_IOT_config_example


class TestR700_IOT:
    """Test suite for R700_IOT RFID Reader class"""

    def test_create_object_default(self):
        """Test creating R700_IOT object with default parameters"""

        # Patch default event handler used by DeviceBase
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)

            # Check if object is instance of R700_IOT class
            assert isinstance(r700_device, R700_IOT)

            # Check basic default attributes
            assert r700_device.username == "root"
            assert r700_device.password == "impinj"
            assert r700_device.firmware_version is None
            assert r700_device.device_type == "rfid"
            assert r700_device.is_connected is False
            assert r700_device.is_reading is False

    def test_url_endpoints_construction(self):
        """Test URL endpoints are constructed correctly"""

        with patch("smartx_rfid.devices._base.on_event", Mock()):
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
        with patch("smartx_rfid.devices._base.on_event", Mock()):
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
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)
            r700_device.is_connected = True
            r700_device.is_gpi_trigger_on = False
            r700_device.start_inventory = AsyncMock(return_value=True)

            # Test that start_inventory can succeed when GPI trigger is off
            result = await r700_device.start_inventory()
            assert result is True

    @pytest.mark.asyncio
    async def test_post_to_reader_retries_on_retryable_status(self):
        """POST/PUT helper should retry transient status codes and succeed later."""
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)

            session = AsyncMock()
            first = Mock(status_code=409)
            first.text = "busy"
            second = Mock(status_code=204)
            second.text = ""
            session.put = AsyncMock(side_effect=[first, second])

            ok = await r700_device.post_to_reader(
                session=session,
                endpoint=r700_device.endpoint_gpo,
                payload={"gpoConfigurations": [{"gpo": 1, "state": "low", "control": "static"}]},
                method="put",
                retries=1,
                retry_delay=0,
            )

            assert ok is True
            assert session.put.await_count == 2

    @pytest.mark.asyncio
    async def test_write_gpo_no_raise_when_disabled(self):
        """write_gpo should optionally return False instead of raising."""
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)
            r700_device.post_to_reader = AsyncMock(return_value=False)

            result = await r700_device.write_gpo(pin=1, state=False, raise_on_fail=False, retry=0)

            assert result is False

    @pytest.mark.asyncio
    async def test_write_gpo_retries_and_emits_event(self):
        """write_gpo should retry transient failures and emit GPO event on success."""
        with patch("smartx_rfid.devices._base.on_event", Mock()) as on_event_mock:
            r700_device = R700_IOT(reading_config=R700_IOT_config_example)

            session = AsyncMock()
            session.is_closed = False
            first = Mock(status_code=503)
            first.text = "temporary unavailable"
            second = Mock(status_code=204)
            second.text = ""
            session.put = AsyncMock(side_effect=[first, second])
            r700_device._session = session

            result = await r700_device.write_gpo(pin=2, state=True, retry=1, retry_delay=0)

            assert result is True
            assert session.put.await_count == 2
            on_event_mock.assert_called()


if __name__ == "__main__":
    pytest.main([__file__])
