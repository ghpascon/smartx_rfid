import pytest
import asyncio
from smartx_rfid.devices import DeviceManager


class TestDeviceManager:
    def test_device_manager_loads_devices(self):
        devices = DeviceManager(devices_path="devices")
        assert devices is not None
        assert len(devices) == 0
        # load devices using the async loader
        asyncio.run(devices._load_devices_async())
        assert len(devices) > 0

    def test_get_device_info(self):
        devices = DeviceManager(devices_path="devices")
        asyncio.run(devices._load_devices_async())
        info = devices.get_device_info()
        assert info is not None
        assert isinstance(info, list)
        assert len(info) > 0


if __name__ == "__main__":
    pytest.main([__file__])
