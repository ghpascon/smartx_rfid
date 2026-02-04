import asyncio
import pytest
from smartx_rfid.devices.printer.SATO._main import SatoPrinter


class DummyEvent:
    def __init__(self):
        self.events = []

    def __call__(self, name, event_type, event_data=None):
        self.events.append((name, event_type, event_data))


def test_sato_init():
    printer = SatoPrinter(ip="127.0.0.1", name="TestSato", port=9100)
    assert printer.name == "TestSato"
    assert printer.device_type == "printer" or printer.device_type == "generic"
    assert printer.ip == "127.0.0.1"
    assert printer.port == 9100
    assert not printer.is_connected


def test_sato_event_callback():
    dummy = DummyEvent()
    printer = SatoPrinter(ip="127.0.0.1", name="TestSato", port=9100)
    printer.on_event = dummy
    printer.on_event(printer.name, "connection", True)
    assert dummy.events[-1] == ("TestSato", "connection", True)


@pytest.mark.asyncio
async def test_sato_connect_disconnect(monkeypatch):
    printer = SatoPrinter(ip="127.0.0.1", name="TestSato", port=9100)

    # Patch asyncio.open_connection to simulate connection
    async def fake_open_connection(ip, port):
        class DummyWriter:
            def is_closing(self):
                return False

            def close(self):
                pass

            async def wait_closed(self):
                pass

            def write(self, data):
                pass

            async def drain(self):
                pass

        return object(), DummyWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    # Run connect in a task and stop after a short time
    async def stop():
        await asyncio.sleep(0.1)
        printer._running = False

    await asyncio.gather(printer.connect(), stop())
    assert not printer.is_connected
