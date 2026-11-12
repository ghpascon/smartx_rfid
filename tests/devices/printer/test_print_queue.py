import asyncio

import pytest

from smartx_rfid.devices.device_manager import DeviceManager
from smartx_rfid.devices.printer import PrintronixPrinter, SatoPrinter, SatoWs4Printer


PRINTERS = [SatoPrinter, SatoWs4Printer, PrintronixPrinter]


@pytest.mark.parametrize("printer_class", PRINTERS)
def test_queue_returns_unique_ids_for_every_job(printer_class):
    printer = printer_class(ip="127.0.0.1")

    ids = printer.add_to_print_queue(["same label", "same label"])
    single_id = printer.add_to_print_queue("another label")

    assert isinstance(ids, list)
    assert len(ids) == 2
    assert len(set(ids)) == 2
    assert single_id not in ids
    assert [job[0] for job in printer._to_print] == [*ids, single_id]
    assert [job[1] for job in printer._to_print] == ["same label", "same label", "another label"]


async def _report_print_success(printer):
    if isinstance(printer, SatoPrinter):
        await printer.on_receive_cmd("a000000")
    elif isinstance(printer, SatoWs4Printer):
        await printer.on_receive_cmd("00000" + "0" * 17)
    else:
        await printer.on_receive_cmd(",".join(["0"] * 12))
        await printer.on_receive_cmd(",".join(["0"] * 11))


@pytest.mark.asyncio
@pytest.mark.parametrize("printer_class", PRINTERS)
async def test_queue_id_is_used_for_send_and_completion_events(printer_class, monkeypatch):
    printer = printer_class(ip="127.0.0.1")
    events = []
    printer.on_event = lambda device, event_type, event_data=None: events.append((event_type, event_data))
    printer.is_connected = True
    printer.can_print = True
    print_id = printer.add_to_print_queue("label with EPC")
    written = []

    async def fake_write(data, verbose=True):
        written.append(data)
        if data != ('! U1 getvar "ezpl.status"\r\n' if isinstance(printer, SatoPrinter) else "~HS"):
            printer.is_connected = False
        return True

    monkeypatch.setattr(printer, "write", fake_write)

    await printer.get_status()
    await asyncio.sleep(0)
    await _report_print_success(printer)

    assert "label with EPC" in written
    assert ("print_sent", print_id) in events
    assert ("print_success", print_id) in events


@pytest.mark.asyncio
@pytest.mark.parametrize("printer_class", PRINTERS)
async def test_send_failure_event_contains_print_id(printer_class, monkeypatch):
    printer = printer_class(ip="127.0.0.1")
    events = []
    printer.on_event = lambda device, event_type, event_data=None: events.append((event_type, event_data))
    printer.is_connected = True
    printer.can_print = True

    async def failed_write(data, verbose=True):
        return False

    monkeypatch.setattr(printer, "write", failed_write)
    success, print_id = printer.print("label")
    await asyncio.sleep(0)

    assert success
    assert ("print_sent_error", {"id": print_id, "error": "Failed to send print data."}) in events
    assert printer._print_sent is False
    assert printer._zpl_id is None


@pytest.mark.asyncio
async def test_device_manager_returns_queue_id_while_printer_is_offline(tmp_path):
    manager = DeviceManager(devices_path=str(tmp_path))
    printer = SatoPrinter(ip="127.0.0.1", name="offline-printer")
    manager.devices.append(printer)

    print_id = manager.add_to_print_queue("offline-printer", "label")

    assert isinstance(print_id, str)
    assert printer._to_print == [(print_id, "label")]
