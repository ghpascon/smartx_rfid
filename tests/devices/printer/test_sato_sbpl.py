import asyncio
import re

import pytest
import pytest_asyncio

from smartx_rfid.devices import DeviceManager, SatoSbplPrinter
from smartx_rfid.devices.printer.SATO_SBPL import SbplLabel
from smartx_rfid.devices.printer.SATO_SBPL.protocol import (
    ACK,
    ESC,
    NAK,
    dc2_application,
    dc2_cancel,
    dc2_delete_all_files,
    dc2_download_file,
    dc2_get_settings,
    dc2_rfid_read,
    dc2_set_settings,
    extract_frames,
    is_dc2_status_frame,
    is_enq_status_frame,
    parse_dc2_status,
    parse_device_info,
    parse_enq_status,
    parse_file_list,
    parse_label_pitch,
    parse_rfid_result,
    parse_sensors,
    parse_settings,
    wrap_frame,
)

STX = b"\x02"
ETX = b"\x03"
DC2 = b"\x12"


# --------------------------------------------------------------------------- #
# Protocol: framing and parsers
# --------------------------------------------------------------------------- #
def test_wrap_frame_is_idempotent():
    assert wrap_frame(b"abc") == STX + b"abc" + ETX
    assert wrap_frame(STX + b"abc" + ETX) == STX + b"abc" + ETX


def test_extract_frames_handles_partial_and_mixed_data():
    buf = bytearray(ACK + STX + b"32,PS0" + ETX + NAK + STX + b"par")
    assert extract_frames(buf) == [("ack", b""), ("frame", b"32,PS0"), ("nak", b"")]
    assert bytes(buf) == STX + b"par"
    buf.extend(b"tial" + ETX)
    assert extract_frames(buf) == [("frame", b"partial")]
    assert not buf


def test_extract_frames_discards_garbage():
    buf = bytearray(b"noise")
    assert extract_frames(buf) == []
    assert not buf


def test_parse_dc2_status_ready():
    status = parse_dc2_status("32,PS0,RS0,RE0,PE0,EN00,BT0,Q000000")
    assert status.state == "standby"
    assert status.can_print and status.is_idle and not status.has_error
    assert status.label == "ready"


def test_parse_dc2_status_printing_and_error():
    printing = parse_dc2_status("32,PS3,RS0,RE0,PE0,EN00,BT0,Q000003")
    assert printing.is_busy and not printing.can_print
    assert printing.remaining == 3
    assert printing.label == "printing"

    error = parse_dc2_status("32,PS5,RS0,RE0,PE0,EN13,BT0,Q000000")
    assert error.has_error and error.error == "head_open"
    assert error.label == "error: head_open"
    assert not error.can_print

    rfid = parse_dc2_status("32,PS5,RS0,RE0,PE0,EN116,BT0,Q000000")
    assert rfid.is_rfid_error and rfid.error == "tag_write_error"


def test_parse_dc2_status_media_empty_blocks_printing():
    status = parse_dc2_status("32,PS0,RS0,RE0,PE2,EN00,BT0,Q000000")
    assert not status.can_print
    assert status.label == "error: media_empty"


def test_parse_dc2_status_invalid():
    with pytest.raises(ValueError):
        parse_dc2_status("garbage")


def test_status_frame_detection():
    assert is_dc2_status_frame(b"32,PS0,RS0,RE0,PE0,EN00,BT0,Q000000")
    assert not is_dc2_status_frame(b"25,1,N,ID:E200")
    assert is_enq_status_frame(b"01A000000")
    assert not is_enq_status_frame(b"32,PS0")


def test_parse_enq_status_standby():
    status = parse_enq_status("01A000000")
    assert status.source == "enq"
    assert status.state == "standby"
    assert status.job_id == "01"


def test_parse_device_info():
    info = parse_device_info("40,MODEL:CL4NX Plus\r\nPR_SN:AB12345\r\nFW:1.0.0\r\n")
    assert info == {"MODEL": "CL4NX Plus", "PR_SN": "AB12345", "FW": "1.0.0"}


def test_parse_sensors_and_label_pitch():
    assert parse_sensors("30,IM:0.2/SL1.5,GAP:0.9/SL1.0") == {"IM": "0.2/SL1.5", "GAP": "0.9/SL1.0"}
    assert parse_label_pitch("10,203,002172") == {"dpi": 203, "pitch_dots": 2172}
    with pytest.raises(ValueError):
        parse_label_pitch("bad")


def test_parse_rfid_result():
    ok = parse_rfid_result("40,1,N,EP:E2000000AAAA,ID:E280689400")
    assert ok.success and ok.error == "N"
    assert ok.epc == "E2000000AAAA"
    assert ok.tid == "E280689400"

    failed = parse_rfid_result("5,0,E,")
    assert not failed.success and failed.error == "E"
    with pytest.raises(ValueError):
        parse_rfid_result("nonsense")


def test_parse_settings_roundtrip():
    data = "SPEED:4\r\nDARK:3\r\n"
    reply = f"99,SB,{len(data)},{data}"
    assert parse_settings(reply) == {"SB": {"SPEED": "4", "DARK": "3"}}


def test_parse_file_list_returns_list():
    assert isinstance(parse_file_list("0"), list)


def test_dc2_builders():
    assert dc2_cancel() == DC2 + b"PH"
    assert dc2_application("SB") == DC2 + b"PI,SB"
    assert dc2_get_settings() == DC2 + b"PB" + b"\x04"
    assert dc2_get_settings("SB", "SPEED") == DC2 + b"PB,SB,SPEED" + b"\x04"
    assert dc2_delete_all_files("SB", 0) == DC2 + b"DH,SB,0,1"
    assert dc2_download_file("A.TTF", b"xyz") == DC2 + b"DE,SB,0,A.TTF,3,xyz"
    assert dc2_rfid_read(("epc", "tid")) == DC2 + b"PJ,U1,U2,NO"
    with pytest.raises(ValueError):
        dc2_rfid_read(("bogus",))


def test_dc2_set_settings_length_prefix():
    cmd = dc2_set_settings({"SB": {"SPEED": 4}})
    match = re.match(rb"\x12PA,(\d+),(.*)$", cmd, re.S)
    assert match is not None
    assert int(match.group(1)) == len(match.group(2))
    assert match.group(2) == b"SB,9,SPEED:4\r\n"


# --------------------------------------------------------------------------- #
# SbplLabel
# --------------------------------------------------------------------------- #
def test_label_minimal_job():
    assert SbplLabel().build() == ESC + b"A" + ESC + b"Q1" + ESC + b"Z"
    assert SbplLabel().build(frame=True) == STX + ESC + b"A" + ESC + b"Q1" + ESC + b"Z" + ETX


def test_label_quantity_is_last():
    job = SbplLabel().text("HI", "XM", x=10, y=20).quantity(5).build()
    assert job.endswith(ESC + b"Q5" + ESC + b"Z")
    assert ESC + b"V20" + ESC + b"H10" + ESC + b"XMHI" in job


def test_label_rfid_commands_come_first():
    job = SbplLabel().text("HI", "XM", x=1, y=1).write_rfid(epc="e2000000aaaa").build()
    assert job.startswith(ESC + b"A" + ESC + b"RU,01" + ESC + b"IP0e:h,epc:E2000000AAAA;")
    assert job.index(b"IP0") < job.index(b"XMHI")


def test_label_rfid_validation():
    with pytest.raises(ValueError):
        SbplLabel().write_rfid()
    with pytest.raises(ValueError):
        SbplLabel().write_rfid(epc="XYZ1")
    with pytest.raises(ValueError):
        SbplLabel().write_rfid(epc="E200", lock="12")


def test_label_validation_of_ranges():
    with pytest.raises(ValueError):
        SbplLabel().quantity(0)
    with pytest.raises(ValueError):
        SbplLabel().text("x", "XM", x=-1)


def test_label_encoding_cp858():
    job = SbplLabel().text("Ação", "XM").build()
    assert "Ação".encode("cp858") in job


def test_label_raw():
    assert b"RAW" in SbplLabel().raw("RAW").build()


# --------------------------------------------------------------------------- #
# Device (offline)
# --------------------------------------------------------------------------- #
def test_device_init():
    printer = SatoSbplPrinter(ip="127.0.0.1", name="SBPL", port=9100)
    assert printer.device_type == "printer"
    assert printer.ip == "127.0.0.1"
    assert printer.port == 9100
    assert not printer.is_connected
    assert not printer.can_print
    assert printer.serial_number is None
    assert printer.print_queue_size == 0


def test_device_invalid_status_mode():
    with pytest.raises(ValueError):
        SatoSbplPrinter(ip="127.0.0.1", status_mode="bad")


def test_device_print_requires_connection():
    printer = SatoSbplPrinter(ip="127.0.0.1")
    assert printer.print("x") == (False, "Printer not connected.")


def test_device_registered_in_manager():
    from smartx_rfid.devices.device_manager import _DEVICE_MAP

    assert _DEVICE_MAP["SATO_SBPL"] is SatoSbplPrinter
    assert DeviceManager is not None


def test_prepare_job_replaces_esc_tag():
    printer = SatoSbplPrinter(ip="127.0.0.1")
    expected = STX + ESC + b"A" + ESC + b"XMHI" + ESC + b"Z" + ETX
    assert printer._prepare_job("<ESC>A<ESC>XMHI<esc>Z") == expected
    assert printer._prepare_job(b"<ESC>A<ESC>XMHI<ESC>Z") == expected


def test_queue_snapshots_and_clear():
    printer = SatoSbplPrinter(ip="127.0.0.1")
    label = SbplLabel().text("A", "XM")
    first = printer.add_to_print_queue(label)
    label.text("B", "XM")
    ids = printer.add_to_print_queue(["raw1", b"raw2"])
    assert isinstance(first, str) and len(ids) == 2
    assert printer.print_queue_size == 3
    assert b"XMB" not in printer._to_print[0][1]
    assert printer._to_print[1][1] == STX + b"raw1" + ETX
    assert printer.clear_print_queue() == 3
    assert printer.print_queue_size == 0


# --------------------------------------------------------------------------- #
# Device (against a fake printer over TCP)
# --------------------------------------------------------------------------- #
class FakePrinter:
    """Minimal SBPL printer emulation (DC2 status/info/RFID + print jobs)."""

    def __init__(self, print_time: float = 0.3):
        self.print_time = print_time
        self.state = 0
        self.error = 0
        self.remaining = 0
        self.jobs: list[bytes] = []
        self.commands: list[bytes] = []
        self.fail_jobs = False
        self.server: asyncio.AbstractServer | None = None
        self.port = 0
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.server.close()
        await self.server.wait_closed()

    @staticmethod
    def _frame(text: str) -> bytes:
        return STX + text.encode("latin-1") + ETX

    def _status(self) -> bytes:
        return self._frame(f"32,PS{self.state},RS0,RE0,PE0,EN{self.error:02d},BT0,Q{self.remaining:06d}")

    async def _finish_job(self):
        await asyncio.sleep(self.print_time)
        if self.fail_jobs:
            self.state, self.error = 5, 116
        else:
            self.state, self.remaining = 0, 0

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        buf = bytearray()
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                buf.extend(data)
                await self._process(buf, writer)
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def _process(self, buf: bytearray, writer: asyncio.StreamWriter):
        while buf:
            if buf[0] == 0x02:
                end = buf.find(ETX)
                if end < 0:
                    return
                job = bytes(buf[1:end])
                del buf[: end + 1]
                self.jobs.append(job)
                self.state, self.remaining = 3, 1
                self._tasks.append(asyncio.create_task(self._finish_job()))
            elif buf[0] == 0x12:
                command = bytes(buf)
                del buf[:]
                self.commands.append(command)
                writer.write(self._answer(command))
                await writer.drain()
            else:
                del buf[0]

    def _answer(self, command: bytes) -> bytes:
        name = command[1:3]
        if name == b"PG":
            return self._status()
        if name == b"PC":
            return self._frame("60,MODEL:CL4NX Plus\r\nPR_SN:SN-TEST-1\r\nFW:1.2.3\r\n")
        if name == b"PD":
            return self._frame("30,IM:0.2/SL1.5,GAP:0.9/SL1.0")
        if name == b"PN":
            return self._frame("10,203,002172")
        if name == b"PK":
            return self._frame("40,1,N,EP:E2000000AAAA,ID:E280689400")
        if name == b"PH":
            self.state, self.remaining = 0, 0
            return ACK
        if name == b"PJ":
            return self._frame("40,EP:E2000000AAAA")
        return ACK


class Events:
    def __init__(self):
        self.items: list[tuple[str, object]] = []

    def __call__(self, device, event_type, event_data=None):
        self.items.append((event_type, event_data))

    def get(self, event_type):
        return [data for kind, data in self.items if kind == event_type]


async def wait_for(condition, timeout: float = 5.0):
    async def _poll():
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(_poll(), timeout)


@pytest_asyncio.fixture
async def fake():
    printer = FakePrinter()
    await printer.start()
    yield printer
    await printer.stop()


@pytest_asyncio.fixture
async def device(fake):
    events = Events()
    sbpl = SatoSbplPrinter(
        ip="127.0.0.1",
        name="SBPL-TEST",
        port=fake.port,
        poll_interval=0.05,
        reconnection_time=0.2,
        print_settle_time=0.1,
        auto_rfid_result=True,
    )
    sbpl.on_event = events
    sbpl.events = events
    task = asyncio.create_task(sbpl.connect())
    await wait_for(lambda: sbpl.can_print)
    yield sbpl
    await sbpl.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_connect_reads_device_info_and_status(device):
    assert device.is_connected
    assert device.serial_number == "SN-TEST-1"
    assert device.model == "CL4NX Plus"
    assert device.events.get("connection")[0] is True
    assert "ready" in device.events.get("status")
    assert device.events.get("device_info")[0]["PR_SN"] == "SN-TEST-1"
    assert device.last_status.can_print


@pytest.mark.asyncio
async def test_print_label_success(device, fake):
    label = SbplLabel().text("HELLO", "XM", x=10, y=10)
    ok, print_id = device.print(label)
    assert ok
    assert device.print("again") == (False, "Printer busy.")

    await wait_for(lambda: device.events.get("print_success"))
    assert device.events.get("print_sent") == [print_id]
    assert device.events.get("print_success") == [print_id]
    assert fake.jobs and b"XMHELLO" in fake.jobs[0]
    assert "printing" in device.events.get("status")
    await wait_for(lambda: device.can_print)


@pytest.mark.asyncio
async def test_print_not_ready_while_printing(device, fake):
    fake.print_time = 1.0
    assert device.print("a")[0]
    await wait_for(lambda: device.last_status.is_busy)
    assert device.print("b") == (False, "Printer busy.")


@pytest.mark.asyncio
async def test_print_rfid_emits_result(device, fake):
    label = SbplLabel().text("TAG", "XM", x=1, y=1).write_rfid(epc="E2000000AAAA")
    ok, print_id = device.print(label)
    assert ok
    await wait_for(lambda: device.events.get("rfid_result"))
    result = device.events.get("rfid_result")[0]
    assert result["id"] == print_id
    assert result["success"] is True
    assert result["epc"] == "E2000000AAAA"
    assert result["tid"] == "E280689400"
    assert b"IP0" in fake.jobs[0]


@pytest.mark.asyncio
async def test_print_error_event(device, fake):
    fake.fail_jobs = True
    ok, print_id = device.print("x")
    assert ok
    await wait_for(lambda: device.events.get("print_error"))
    assert device.events.get("print_error") == [print_id]
    assert any(label.startswith("error: tag_write_error") for label in device.events.get("status"))
    assert not device.can_print


@pytest.mark.asyncio
async def test_print_queue_is_processed_in_order(device, fake):
    fake.print_time = 0.15
    ids = device.add_to_print_queue([SbplLabel().text("ONE", "XM"), SbplLabel().text("TWO", "XM")])
    await wait_for(lambda: len(device.events.get("print_success")) == 2, timeout=10)
    assert device.events.get("print_success") == ids
    assert b"XMONE" in fake.jobs[0] and b"XMTWO" in fake.jobs[1]
    assert device.print_queue_size == 0


@pytest.mark.asyncio
async def test_queries(device, fake):
    status = await device.get_printer_status()
    assert status is not None and status.state in ("standby", "printing")
    assert (await device.get_device_info())["MODEL"] == "CL4NX Plus"
    assert (await device.get_sensor_info())["GAP"] == "0.9/SL1.0"
    assert await device.get_label_pitch() == {"dpi": 203, "pitch_dots": 2172}
    assert (await device.read_rfid_result()).epc == "E2000000AAAA"
    assert (await device.read_rfid())["epc"] == "E2000000AAAA"


@pytest.mark.asyncio
async def test_status_info_only_emitted_on_change(device):
    await asyncio.sleep(0.4)  # several polls on an unchanged printer
    assert len(device.events.get("status_info")) == 1
    before = list(device.events.items)
    device._on_message("frame", b"01A000000")  # unsolicited ENQ-format status (dc2 mode): ignored
    assert device.events.items == before


@pytest.mark.asyncio
async def test_manager_read_rfid(device):
    manager = DeviceManager(devices_path="unused")
    manager.devices = [device]
    ok, tag = await manager.read_rfid("SBPL-TEST", ("epc",))
    assert ok and tag["epc"] == "E2000000AAAA"
    ok, msg = await manager.read_rfid("missing")
    assert not ok and "not found" in msg


@pytest.mark.asyncio
async def test_settings_and_control_commands(device, fake):
    assert await device.set_settings({"SB": {"SPEED": 4}})
    assert any(c.startswith(DC2 + b"PA,") and b"SPEED:4" in c for c in fake.commands)
    assert await device.set_application("SB")
    assert await device.cancel_print()
    assert await device.initialize_settings("SB")
    assert any(c.startswith(DC2 + b"PI,SB") for c in fake.commands)


@pytest.mark.asyncio
async def test_system_jobs_are_framed(device, fake):
    assert await device.feed()
    assert await device.reprint()
    assert await device.set_rfid_power(20.5, 15)
    await wait_for(lambda: len(fake.jobs) >= 3)
    assert fake.jobs[0] == ESC + b"A" + ESC + b"IK0" + ESC + b"Z"
    assert fake.jobs[1] == ESC + b"A" + ESC + b"C" + ESC + b"Z"
    assert b"IP5205,150" in fake.jobs[2]


@pytest.mark.asyncio
async def test_write_raw(device, fake):
    assert await device.write(b"\x12PG", verbose=False)
    await wait_for(lambda: any(c.startswith(DC2 + b"PG") for c in fake.commands[1:]))


@pytest.mark.asyncio
async def test_reconnects_after_connection_loss(device, fake):
    fake.server.close()
    device.writer.close()
    await wait_for(lambda: device.events.get("connection")[-1] is False, timeout=5)
    assert device.serial_number is None
    assert not device.can_print
