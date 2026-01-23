import pytest
from smartx_rfid.devices import DeviceManager


class TestDeviceManager:
    def test_device_manager(self):
        devices = DeviceManager(devices_path="devices")
        assert devices is not None
        assert len(devices) == 0
        devices.load_devices()
        assert len(devices) == 2


if __name__ == "__main__":
    pytest.main([__file__])
