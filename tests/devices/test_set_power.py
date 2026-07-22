import json
import pytest


from smartx_rfid.devices.device_manager import DeviceManager


class DummyDevice:
    def __init__(self, name):
        self.name = name
        self.is_connected = True
        self.device_type = "rfid"

    async def shutdown(self):
        return None

    def cancel_all(self):
        return None


@pytest.mark.asyncio
async def test_set_power(tmp_path, monkeypatch):
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir()

    name = "mydev"
    filepath = devices_dir / f"{name}.json"

    config = {
        "reader": "SERIAL",
        "read_power": 10,
        "antenna": {"power": 15, "config": {"transmitPowerCdBm": 18}},
    }

    filepath.write_text(json.dumps(config), encoding="utf-8")

    manager = DeviceManager(devices_path=str(devices_dir))

    # Ensure manager has a device so get_device finds it
    manager.devices.append(DummyDevice(name))

    # Patch _add_device to avoid instantiating real device classes during reload
    def fake_add_device(name_arg, reader, data):
        manager.devices.append(DummyDevice(name_arg))

    monkeypatch.setattr(manager, "_add_device", fake_add_device)

    success, msg = await manager.set_power(name, 30)

    assert success is True
    assert "set to 30" in msg

    with open(str(filepath), "r", encoding="utf-8") as f:
        new_conf = json.load(f)

    assert new_conf["read_power"] == 30
    assert new_conf["antenna"]["power"] == 30
    assert new_conf["antenna"]["config"]["transmitPowerCdBm"] == 30
