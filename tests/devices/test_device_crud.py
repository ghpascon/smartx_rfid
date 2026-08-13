"""
Testes para as operações CRUD do DeviceManager
================================================

Usa diretório temporário (pytest tmp_path) para garantir isolamento total
entre testes sem modificar o diretório real de devices.
"""

import json
import os
import asyncio

import pytest

from smartx_rfid.devices import DeviceManager

# ---------------------------------------------------------------------------
# Payloads de teste
# ---------------------------------------------------------------------------

TCP_CONFIG = {
    "READER": "TCP",
    "IP": "192.168.1.10",
    "PORT": 23,
}

TCP_CONFIG_UPDATED = {
    "READER": "TCP",
    "IP": "10.0.0.99",
    "PORT": 9090,
}

SERIAL_CONFIG = {
    "READER": "SERIAL",
    "PORT": "AUTO",
    "BAUDRATE": 9600,
    "VID": 259,
    "PID": 24673,
}

INVALID_CONFIG_NO_READER = {
    "IP": "192.168.1.10",
    "PORT": 23,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path):
    """DeviceManager apontando para diretório temporário vazio."""
    return DeviceManager(devices_path=str(tmp_path))


@pytest.fixture
def manager_with_tcp(tmp_path):
    """DeviceManager com um device TCP pré-criado no disco."""
    m = DeviceManager(devices_path=str(tmp_path))
    ok, _ = asyncio.run(m.create_device_config("leitor_tcp", TCP_CONFIG))
    assert ok
    return m


# ---------------------------------------------------------------------------
# create_device_config
# ---------------------------------------------------------------------------


class TestCreateDeviceConfig:
    def test_create_success(self, manager, tmp_path):
        ok, err = asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))

        assert ok is True
        assert err is None
        assert os.path.exists(tmp_path / "leitor.json")

    def test_create_writes_valid_json(self, manager, tmp_path):
        asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))

        with open(tmp_path / "leitor.json", encoding="utf-8") as f:
            saved = json.load(f)
        # DeviceManager normaliza chaves para lower-case ao salvar
        assert saved["reader"] == "TCP"
        assert saved["ip"] == TCP_CONFIG["IP"]

    def test_create_reloads_device_list(self, manager):
        assert manager.get_device_count() == 0

        asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))

        assert manager.get_device_count() == 1
        assert "leitor" in manager.get_devices()

    def test_create_multiple_devices(self, manager):
        asyncio.run(manager.create_device_config("tcp1", TCP_CONFIG))
        asyncio.run(manager.create_device_config("serial1", SERIAL_CONFIG))

        assert manager.get_device_count() == 2
        assert set(manager.get_devices()) == {"tcp1", "serial1"}

    def test_create_duplicate_without_overwrite_fails(self, manager):
        asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))
        ok, err = asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))

        assert ok is False
        assert err is not None
        assert "already exists" in err

    def test_create_with_overwrite_succeeds(self, manager, tmp_path):
        asyncio.run(manager.create_device_config("leitor", TCP_CONFIG))
        ok, err = asyncio.run(manager.create_device_config("leitor", TCP_CONFIG_UPDATED, overwrite=True))

        assert ok is True
        assert err is None

        with open(tmp_path / "leitor.json", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["ip"] == TCP_CONFIG_UPDATED["IP"]

    def test_create_invalid_config_no_reader(self, manager, tmp_path):
        ok, err = asyncio.run(manager.create_device_config("invalido", INVALID_CONFIG_NO_READER))

        assert ok is False
        assert "reader" in (err or "").lower()
        assert not os.path.exists(tmp_path / "invalido.json")

    def test_create_does_not_reload_on_failure(self, manager):
        # Device inválido não deve aparecer na lista
        asyncio.run(manager.create_device_config("invalido", INVALID_CONFIG_NO_READER))
        assert "invalido" not in manager.get_devices()


# ---------------------------------------------------------------------------
# update_device_config
# ---------------------------------------------------------------------------


class TestUpdateDeviceConfig:
    @pytest.mark.asyncio
    async def test_update_existing_device(self, manager_with_tcp, tmp_path):
        ok, err = await manager_with_tcp.update_device_config("leitor_tcp", TCP_CONFIG_UPDATED)

        assert ok is True
        assert err is None

    @pytest.mark.asyncio
    async def test_update_changes_file_contents(self, manager_with_tcp, tmp_path):
        await manager_with_tcp.update_device_config("leitor_tcp", TCP_CONFIG_UPDATED)

        with open(tmp_path / "leitor_tcp.json", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["ip"] == TCP_CONFIG_UPDATED["IP"]
        assert saved["port"] == TCP_CONFIG_UPDATED["PORT"]

    @pytest.mark.asyncio
    async def test_update_reloads_device_list(self, manager_with_tcp):
        await manager_with_tcp.update_device_config("leitor_tcp", TCP_CONFIG_UPDATED)

        assert "leitor_tcp" in manager_with_tcp.get_devices()
        assert manager_with_tcp.get_device_count() == 1

    @pytest.mark.asyncio
    async def test_update_creates_new_if_not_exists(self, manager, tmp_path):
        """update_device_config (overwrite=True) cria se não existir."""
        ok, err = await manager.update_device_config("novo", TCP_CONFIG)

        assert ok is True
        assert os.path.exists(tmp_path / "novo.json")

    @pytest.mark.asyncio
    async def test_update_invalid_config_fails(self, manager_with_tcp):
        ok, err = await manager_with_tcp.update_device_config("leitor_tcp", INVALID_CONFIG_NO_READER)

        assert ok is False
        assert err is not None

    @pytest.mark.asyncio
    async def test_update_with_active_tasks_does_not_deadlock(self, manager_with_tcp, monkeypatch):
        """Regressão: update não deve travar quando já existem connect tasks ativas."""

        started_devices = []

        async def fake_connect_runner(device):
            started_devices.append(device.name)

        monkeypatch.setattr(manager_with_tcp, "_device_connect_runner", fake_connect_runner)

        blocker = asyncio.Event()

        async def keep_alive_task():
            await blocker.wait()

        pending_task = asyncio.create_task(keep_alive_task())
        await manager_with_tcp._register_connect_task("outra_task", pending_task)

        try:
            ok, err = await asyncio.wait_for(
                manager_with_tcp.update_device_config("leitor_tcp", TCP_CONFIG_UPDATED),
                timeout=2.0,
            )
        finally:
            blocker.set()
            await manager_with_tcp._cancel_connect_tasks()

        assert ok is True
        assert err is None
        assert "leitor_tcp" in started_devices


# ---------------------------------------------------------------------------
# delete_device_config
# ---------------------------------------------------------------------------


class TestDeleteDeviceConfig:
    @pytest.mark.asyncio
    async def test_delete_existing_device(self, manager_with_tcp, tmp_path):
        ok, err = await manager_with_tcp.delete_device_config("leitor_tcp")

        assert ok is True
        assert err is None
        assert not os.path.exists(tmp_path / "leitor_tcp.json")

    @pytest.mark.asyncio
    async def test_delete_reloads_device_list(self, manager_with_tcp):
        assert manager_with_tcp.get_device_count() == 1

        await manager_with_tcp.delete_device_config("leitor_tcp")

        assert manager_with_tcp.get_device_count() == 0
        assert "leitor_tcp" not in manager_with_tcp.get_devices()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_fails(self, manager):
        ok, err = await manager.delete_device_config("nao_existe")

        assert ok is False
        assert err is not None
        assert "not found" in (err or "").lower()

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_devices(self, manager, tmp_path):
        await manager.create_device_config("tcp1", TCP_CONFIG)
        await manager.create_device_config("serial1", SERIAL_CONFIG)

        await manager.delete_device_config("tcp1")

        assert manager.get_device_count() == 1
        assert "serial1" in manager.get_devices()
        assert "tcp1" not in manager.get_devices()


# ---------------------------------------------------------------------------
# example_path (fix: não adiciona subpasta 'devices')
# ---------------------------------------------------------------------------


class TestExamplePath:
    def test_get_device_types_example(self, tmp_path):
        # Salva arquivos JSON diretamente no tmp_path (sem subpasta 'devices')
        (tmp_path / "TCP.json").write_text(json.dumps(TCP_CONFIG))
        (tmp_path / "SERIAL.json").write_text(json.dumps(SERIAL_CONFIG))

        manager = DeviceManager(devices_path=str(tmp_path), example_path=str(tmp_path))
        types = manager.get_device_types_example()

        assert set(types) == {"TCP", "SERIAL"}

    def test_get_device_config_example(self, tmp_path):
        (tmp_path / "TCP.json").write_text(json.dumps(TCP_CONFIG))

        manager = DeviceManager(devices_path=str(tmp_path), example_path=str(tmp_path))
        config = manager.get_device_config_example("TCP")

        assert config is not None
        assert config["READER"] == "TCP"

    def test_get_device_config_example_missing(self, tmp_path):
        manager = DeviceManager(devices_path=str(tmp_path), example_path=str(tmp_path))
        config = manager.get_device_config_example("INEXISTENTE")

        assert config is None

    def test_get_device_types_example_empty_path(self, tmp_path):
        manager = DeviceManager(devices_path=str(tmp_path), example_path="")
        assert manager.get_device_types_example() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
