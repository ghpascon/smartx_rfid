"""Communication helpers for :class:`SatoSbplPrinter` (receive loop, status polling, queries, commands)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from .label import SbplLabel
from .protocol import (
    ENQ,
    ESC,
    PrinterStatus,
    RfidResult,
    dc2_application,
    dc2_cancel,
    dc2_delete_all_files,
    dc2_delete_file,
    dc2_device_info,
    dc2_download_file,
    dc2_get_settings,
    dc2_initialize,
    dc2_label_pitch,
    dc2_list_files,
    dc2_power_off,
    dc2_restart,
    dc2_rfid_read,
    dc2_rfid_result,
    dc2_sensors,
    dc2_set_settings,
    dc2_status,
    extract_frames,
    is_dc2_status_frame,
    is_enq_status_frame,
    parse_device_info,
    parse_dc2_status,
    parse_enq_status,
    parse_file_list,
    parse_label_pitch,
    parse_rfid_read,
    parse_rfid_result,
    parse_sensors,
    parse_settings,
    wrap_frame,
)

PrintData = str | bytes | SbplLabel

DRAIN_TIMEOUT = 5.0
_ESC_TAG = re.compile(rb"<ESC>", re.IGNORECASE)


@dataclass
class _Pending:
    kind: str  # "status" | "frame" | "ack"
    future: asyncio.Future


class Helpers:
    """Connection, polling and command helpers."""

    # ------------------------------------------------------------------ #
    # Data preparation / sending
    # ------------------------------------------------------------------ #
    def _prepare_job(self, data: PrintData) -> bytes:
        """Convert a label/str/bytes into a framed (``STX ... ETX``) SBPL job.

        Raw ``str``/``bytes`` jobs may use the literal text ``<ESC>``, which is replaced by the ESC byte (0x1B).
        """
        if isinstance(data, SbplLabel):
            payload = data.build()
        elif isinstance(data, str):
            payload = _ESC_TAG.sub(ESC, data.encode(self.encoding, errors="replace"))
        else:
            payload = _ESC_TAG.sub(ESC, bytes(data))
        return wrap_frame(payload)

    async def _send(self, data: bytes) -> bool:
        """Write bytes to the socket (serialized, with drain timeout)."""
        if not self.is_connected or not self.writer:
            return False
        async with self._write_lock:
            try:
                self.writer.write(data)
                await asyncio.wait_for(self.writer.drain(), timeout=DRAIN_TIMEOUT)
                return True
            except Exception as e:
                logging.warning(f"[{self.name}] [SEND ERROR] {type(e).__name__}: {e}")
                if self.is_connected:
                    self.is_connected = False
                return False

    # ------------------------------------------------------------------ #
    # Request / response
    # ------------------------------------------------------------------ #
    async def _request(self, command: bytes, kind: str, timeout: float) -> tuple[str, bytes] | None:
        """Send ``command`` and wait for its reply. Returns ``(type, payload)`` or ``None`` on timeout."""
        async with self._request_lock:
            if not self.is_connected or not self.writer:
                return None
            pending = _Pending(kind, asyncio.get_running_loop().create_future())
            self._pending = pending
            try:
                if not await self._send(command):
                    return None
                return await asyncio.wait_for(pending.future, timeout=timeout)
            except asyncio.TimeoutError:
                return None
            finally:
                self._pending = None

    async def _query(self, command: bytes, timeout: float = 2.0) -> bytes | None:
        """Request a framed reply. Returns the payload or ``None`` (timeout or NAK)."""
        result = await self._request(command, "frame", timeout)
        if result is None or result[0] != "frame":
            return None
        return result[1]

    async def _command(self, command: bytes, timeout: float = 2.0) -> bool:
        """Send a command that is answered with ACK/NAK."""
        result = await self._request(command, "ack", timeout)
        return result is not None and result[0] == "ack"

    def _resolve(self, kind: str, payload: bytes) -> bool:
        pending = self._pending
        if pending is None or pending.future.done():
            return False
        pending.future.set_result((kind, payload))
        return True

    def _on_message(self, kind: str, payload: bytes) -> None:
        pending = self._pending
        if kind == "nak":
            self._resolve("nak", b"")
            return
        if kind == "ack":
            if pending is not None and pending.kind == "ack":
                self._resolve("ack", b"")
            return

        if is_dc2_status_frame(payload) or is_enq_status_frame(payload):
            if pending is not None and pending.kind == "status" and self._resolve("frame", payload):
                return
            try:
                self._apply_status(self._parse_status(payload))
            except ValueError as e:
                logging.debug(f"[{self.name}] ignoring status frame: {e}")
            return

        if pending is not None and pending.kind == "frame" and self._resolve("frame", payload):
            return
        self.emit_event("message", payload.decode("latin-1", errors="replace"))

    @staticmethod
    def _parse_status(payload: bytes) -> PrinterStatus:
        return parse_dc2_status(payload) if is_dc2_status_frame(payload) else parse_enq_status(payload)

    # ------------------------------------------------------------------ #
    # Receive / status loops
    # ------------------------------------------------------------------ #
    async def receive_data(self):
        """Read the socket and dispatch complete SBPL frames."""
        try:
            while True:
                data = await self.reader.read(4096)
                if not data:
                    raise ConnectionError("Connection lost")
                self._rx_buffer.extend(data)
                for kind, payload in extract_frames(self._rx_buffer):
                    self._on_message(kind, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"[{self.name}] [RECEIVE ERROR] {e}")
            self.is_connected = False

    async def get_status(self):
        """Poll the printer status and feed the print queue."""
        await self._load_device_info()
        failures = 0
        while self.is_connected:
            await asyncio.sleep(self.poll_interval)
            if (self.writer and self.writer.is_closing()) or (self.reader and self.reader.at_eof()):
                self.is_connected = False
                break

            result = await self._request(
                ENQ if self.status_mode == "enq" else dc2_status(), "status", self.status_timeout
            )
            if result is None:
                failures += 1
                if failures >= self.max_status_failures:
                    logging.error(f"[{self.name}] no status reply ({failures} attempts), reconnecting")
                    self.is_connected = False
                    break
                continue
            failures = 0
            kind, payload = result
            if kind == "frame":
                try:
                    self._apply_status(self._parse_status(payload))
                except ValueError as e:
                    logging.warning(f"[{self.name}] invalid status reply: {e}")
                    continue
            else:
                continue  # NAK: printer busy acquiring sensor info

            await self._process_print_progress()
            await self._process_queue()

    async def _load_device_info(self) -> None:
        info = await self.get_device_info(timeout=5.0)
        if not info:
            return
        self.device_info = info
        self.model = info.get("MODEL")
        self.serial_number = info.get("PR_SN") or None
        self.emit_event("device_info", dict(info))

    # ------------------------------------------------------------------ #
    # Status handling
    # ------------------------------------------------------------------ #
    def _apply_status(self, status: PrinterStatus) -> None:
        previous = self.last_status
        self.last_status = status
        self.can_print = status.can_print
        if previous is None or previous.label != status.label:
            self.emit_event("status", status.label)
        if previous != status:
            self.emit_event("status_info", status.as_dict())

    async def _process_print_progress(self) -> None:
        """Decide whether the job in progress finished, failed or is still running."""
        if not self._print_sent:
            return
        status = self.last_status
        print_id = self._print_id
        if status.has_error:
            self._reset_print_tracking()
            self.emit_event("print_error", f"{print_id}")
            return
        if status.is_busy:
            self._print_started = True
            return
        settled = time.monotonic() - self._print_sent_at >= self.print_settle_time
        if status.is_idle and (self._print_started or settled):
            has_rfid = self._print_has_rfid
            self._reset_print_tracking()
            self.emit_event("print_success", f"{print_id}")
            if has_rfid and self.auto_rfid_result:
                result = await self.read_rfid_result()
                if result is not None:
                    self.emit_event("rfid_result", {"id": print_id, **result.as_dict()})

    async def _process_queue(self) -> None:
        if self._to_print and self.can_print and not self._print_sent:
            print_id, job = self._to_print.pop(0)
            logging.info(f"{self.name} - Sending: Print ID: {print_id}, {len(self._to_print)} left.")
            status, msg = self.print(job, print_id=print_id)
            if not status:
                self.emit_event("print_sent_error", {"id": print_id, "error": msg})

    def _reset_print_tracking(self) -> None:
        self._print_sent = False
        self._print_started = False
        self._print_id = None
        self._print_has_rfid = False

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    async def get_printer_status(self, timeout: float = 2.0) -> PrinterStatus | None:
        """Request the printer status (``DC2 PG``) and return it decoded."""
        result = await self._request(dc2_status(), "status", timeout)
        if result is None or result[0] != "frame":
            return None
        try:
            status = parse_dc2_status(result[1])
        except ValueError:
            return None
        self._apply_status(status)
        return status

    async def get_device_info(self, timeout: float = 2.0) -> dict[str, str] | None:
        """Device information (``DC2 PC``): model, firmware, counters, MAC, serial (``PR_SN``)."""
        payload = await self._query(dc2_device_info(), timeout)
        return parse_device_info(payload) if payload is not None else None

    async def get_sensor_info(self, timeout: float = 2.0) -> dict[str, str] | None:
        """Sensor levels (``DC2 PD``): IM, GAP, HEAD OPEN, CUTTER OPEN, HEAD TEMP, RIBBON ..."""
        payload = await self._query(dc2_sensors(), timeout)
        return parse_sensors(payload) if payload is not None else None

    async def get_label_pitch(self, timeout: float = 2.0) -> dict[str, int] | None:
        """Head density and measured label pitch (``DC2 PN``)."""
        payload = await self._query(dc2_label_pitch(), timeout)
        if payload is None:
            return None
        try:
            return parse_label_pitch(payload)
        except ValueError:
            return None

    async def get_settings(
        self, identifier: str | None = None, *items: str, timeout: float = 3.0
    ) -> dict[str, dict[str, str]] | None:
        """Printer settings (``DC2 PB``) as ``{identifier: {name: value}}``."""
        payload = await self._query(dc2_get_settings(identifier, *items), timeout)
        return parse_settings(payload) if payload is not None else None

    async def set_settings(self, settings: dict[str, dict[str, Any]], timeout: float = 3.0) -> bool:
        """Change printer settings (``DC2 PA``), e.g. ``{"SB": {"SPEED": 4}}``."""
        return await self._command(dc2_set_settings(settings), timeout)

    async def read_rfid_result(self, timeout: float = 2.0, retries: int = 3) -> RfidResult | None:
        """EPC/TID result of the last RFID write (``DC2 PK``). Requires the label to enable ``<RU>``."""
        for attempt in range(retries):
            payload = await self._query(dc2_rfid_result(), timeout)
            if payload is not None:
                try:
                    return parse_rfid_result(payload)
                except ValueError:
                    return None
            if attempt + 1 < retries:
                await asyncio.sleep(0.3)  # NAK while the printer is still busy
        return None

    async def read_rfid(
        self, areas: tuple[str, ...] = ("epc",), option: str = "NO", timeout: float = 8.0
    ) -> dict[str, Any] | None:
        """Read the tag in front of the antenna (``DC2 PJ``): epc, tid, user, pc areas."""
        payload = await self._query(dc2_rfid_read(areas, option), timeout)
        return parse_rfid_read(payload) if payload is not None else None

    async def list_files(self, language: str = "SB", file_type: int = 0, timeout: float = 3.0) -> list[str] | None:
        """Names of the files stored in the printer (``DC2 DF``)."""
        payload = await self._query(dc2_list_files(language, file_type), timeout)
        return parse_file_list(payload) if payload is not None else None

    # ------------------------------------------------------------------ #
    # Printer control (DC2)
    # ------------------------------------------------------------------ #
    async def cancel_print(self, timeout: float = 3.0) -> bool:
        """Cancel the running job and clear the receive buffer (``DC2 PH``)."""
        ok = await self._command(dc2_cancel(), timeout)
        if ok and self._print_sent:
            self._reset_print_tracking()
        return ok

    async def restart(self) -> bool:
        """Restart the printer (``DC2 DC``)."""
        return await self._send(dc2_restart())

    async def power_off(self) -> bool:
        """Turn the printer off (``DC2 DD``)."""
        return await self._send(dc2_power_off())

    async def initialize_settings(self, identifier: str = "SB", timeout: float = 5.0) -> bool:
        """Restore a settings section to factory values (``DC2 DB``): CA, SB, IL, IF, CX ..."""
        return await self._command(dc2_initialize(identifier), timeout)

    async def set_application(self, identifier: str = "SB", timeout: float = 3.0) -> bool:
        """Switch the printer language: ``SB`` SBPL, ``SZ`` SZPL, ``SI`` SIPL, ``00`` auto ..."""
        return await self._command(dc2_application(identifier), timeout)

    async def download_file(
        self, name: str, data: bytes, language: str = "SB", file_type: int = 0, timeout: float = 30.0
    ) -> bool:
        """Store a file (font/logo/TrueType) in the printer (``DC2 DE``)."""
        return await self._command(dc2_download_file(name, data, language, file_type), timeout)

    async def delete_file(self, name: str, language: str = "SB", file_type: int = 0, timeout: float = 5.0) -> bool:
        return await self._command(dc2_delete_file(name, language, file_type), timeout)

    async def delete_all_files(self, language: str = "SB", file_type: int = 0, timeout: float = 5.0) -> bool:
        return await self._command(dc2_delete_all_files(language, file_type), timeout)

    # ------------------------------------------------------------------ #
    # Printer control (SBPL jobs)
    # ------------------------------------------------------------------ #
    async def send_job(self, data: PrintData, verbose: bool = True) -> bool:
        """Send an SBPL job without status checks (use :meth:`print` for tracked printing)."""
        job = self._prepare_job(data)
        ok = await self._send(job)
        if ok and verbose:
            logging.info(f"[{self.name}] [SENT] {len(job)} bytes")
        return ok

    async def _system_job(self, *commands: bytes) -> bool:
        return await self.send_job(ESC + b"A" + b"".join(ESC + c for c in commands) + ESC + b"Z", verbose=False)

    async def feed(self, dots: int | None = None) -> bool:
        """Feed one label, or ``dots`` dots (``<IK>0``)."""
        return await self._system_job(b"IK0" if dots is None else f"IK0,{int(dots)}".encode())

    async def backfeed(self, dots: int) -> bool:
        """Back feed ``dots`` dots (``<IK>1``, 6 to 60 mm)."""
        return await self._system_job(f"IK1,{int(dots)}".encode())

    async def reprint(self) -> bool:
        """Reprint the last label (``<C>``)."""
        return await self._system_job(b"C")

    async def cut(self) -> bool:
        """Eject and cut the label left in the printer (``<NC>``). Cutter models only."""
        return await self._system_job(b"NC")

    async def tear_off(self) -> bool:
        """Force tear-off without waiting for the tear-off timer (``<TK>``)."""
        return await self._system_job(b"TK")

    async def clear_buffer(self, everything: bool = False) -> bool:
        """Clear receive/edit buffers (``<*>``); ``everything=True`` also clears user characters and overlays."""
        ok = await self._system_job(b"*X" if everything else b"*")
        await asyncio.sleep(0.1)  # required interval before sending new data
        return ok

    async def set_offline(self) -> bool:
        """Put the printer offline (``<@>``)."""
        return await self._system_job(b"@")

    async def set_speed(self, speed: int) -> bool:
        return await self._system_job(f"CS{int(speed)}".encode())

    async def set_darkness(self, level: int, mode: str = "A") -> bool:
        return await self._system_job(f"#F{int(level)}{mode}".encode())

    async def set_print_mode(self, mode: str | int) -> bool:
        return await self._system_job(f"PM{mode}".encode())

    async def set_sensor(self, sensor_type: str | int) -> bool:
        types = {"reflective": "0", "gap": "1", "none": "2", 0: "0", 1: "1", 2: "2"}
        if sensor_type not in types:
            raise ValueError("sensor must be 'reflective', 'gap' or 'none'")
        return await self._system_job(f"IG{types[sensor_type]}".encode())

    async def set_rfid_power(self, write_dbm: float, read_dbm: float | None = None) -> bool:
        """Antenna output power in dBm (``<IP5>``)."""
        params = f"{round(write_dbm * 10):03d}"
        if read_dbm is not None:
            params += f",{round(read_dbm * 10):03d}"
        return await self._system_job(f"IP5{params}".encode())
