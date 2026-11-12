import asyncio
import logging
import time
import uuid
from typing import Optional

from smartx_rfid.devices._base import DeviceBase

from .helpers import Helpers, PrintData, _Pending
from .protocol import PrinterStatus


class SatoSbplPrinter(DeviceBase, Helpers):
    """SATO printer driven by SBPL (CL4NX Plus / CL6NX Plus and compatible).

    The printer is reached over TCP (port 9100 by default). Status is polled with ``DC2 PG`` and
    jobs are tracked until the printer is idle again, emitting the same events as the other printers:

    - ``status``: ``ready``, ``printing``, ``analyzing``, ``waiting_dispense``, ``offline``, ``error: <name>``
    - ``status_info``: full decoded status (dict)
    - ``print_sent`` / ``print_sent_error`` / ``print_success`` / ``print_error``
    - ``rfid_result``: EPC/TID result of the last RFID write (when ``auto_rfid_result=True``)
    - ``device_info``: model, firmware and serial number read on connection

    Args:
        ip: Printer IP address.
        name: Device name.
        port: TCP port (9100 = single connection for data and status).
        reconnection_time: Seconds between reconnection attempts.
        encoding: Python codec used to encode ``str`` jobs (``cp858`` is the SBPL default code page).
        status_mode: ``"dc2"`` (``DC2 PG``, default) or ``"enq"`` (``ENQ`` for Status3/Status4).
        poll_interval: Seconds between status polls.
        status_timeout: Seconds to wait for each status reply.
        max_status_failures: Consecutive status timeouts before reconnecting.
        print_settle_time: Seconds to wait before accepting an idle printer as "job done" when
            the job was never seen busy (very fast jobs).
        auto_rfid_result: Read ``DC2 PK`` after a successful job that wrote an RFID tag.
    """

    def __init__(
        self,
        ip: str,
        name: str = "SatoSbpl",
        port: int = 9100,
        reconnection_time: int = 3,
        encoding: str = "cp858",
        status_mode: str = "dc2",
        poll_interval: float = 0.5,
        status_timeout: float = 2.0,
        max_status_failures: int = 3,
        print_settle_time: float = 1.5,
        auto_rfid_result: bool = False,
        **kwargs,
    ):
        DeviceBase.__init__(self)
        if status_mode not in ("dc2", "enq"):
            raise ValueError("status_mode must be 'dc2' or 'enq'")
        self.name = name
        self.device_type = "printer"
        self.ip = ip
        self.port = port
        self.reconnection_time = reconnection_time
        self.encoding = encoding
        self.status_mode = status_mode
        self.poll_interval = poll_interval
        self.status_timeout = status_timeout
        self.max_status_failures = max_status_failures
        self.print_settle_time = print_settle_time
        self.auto_rfid_result = auto_rfid_result

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self.serial_number: Optional[str] = None
        self.model: Optional[str] = None
        self.device_info: dict[str, str] = {}

        self.can_print = False
        self.last_status: Optional[PrinterStatus] = None

        self._to_print: list[tuple[str, bytes]] = []
        self._rx_buffer = bytearray()
        self._pending: Optional[_Pending] = None
        self._write_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

        # Print tracking
        self._print_sent = False
        self._print_started = False
        self._print_sent_at = 0.0
        self._print_id: Optional[str] = None
        self._print_has_rfid = False
        self._queue_blocked_logged_at = 0.0

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    async def connect(self):
        """Connect to the printer and keep the connection alive."""
        while self._running:
            tasks: list[asyncio.Task] = []
            try:
                logging.info(f"Connecting: {self.name} - {self.ip}:{self.port}")
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=3
                )
                self._rx_buffer.clear()
                self.is_connected = True

                tasks = [
                    self.create_task(self.receive_data()),
                    self.create_task(self.get_status()),
                ]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"[{self.name}] [CONNECTION ERROR] {e}")
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await self._teardown_connection()

            if not self._running:
                break
            await asyncio.sleep(self.reconnection_time)

    async def _teardown_connection(self):
        """Single place that releases the TCP connection and resets the connection state."""
        self.is_connected = False
        self.is_reading = False
        self.serial_number = None
        self.can_print = False
        self.last_status = None
        self._rx_buffer.clear()
        self._reset_print_tracking()
        pending = self._pending
        if pending is not None and not pending.future.done():
            pending.future.set_result(("closed", b""))
        writer = self.writer
        if writer is not None:
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except Exception:
                pass
        self.reader = None
        self.writer = None

    async def close(self):
        """Stop the connection loop and release resources."""
        self._running = False
        await self._teardown_connection()
        await self.shutdown()

    # ------------------------------------------------------------------ #
    # Printing
    # ------------------------------------------------------------------ #
    async def write(self, data: str | bytes, verbose: bool = True) -> bool:
        """Send raw bytes/text to the printer (no framing is added)."""
        raw = data.encode(self.encoding, errors="replace") if isinstance(data, str) else bytes(data)
        ok = await self._send(raw)
        if ok and verbose:
            logging.info(f"[{self.name}] [SENT] {len(raw)} bytes")
        return ok

    def print(self, sbpl: PrintData, print_id: str | None = None):
        """Send an SBPL job (``SbplLabel``, ``str`` or ``bytes``) to the printer.

        Returns ``(True, print_id)`` or ``(False, reason)``.
        """
        if not self.is_connected:
            return False, "Printer not connected."
        if self._print_sent:
            return False, "Printer busy."
        if not self.can_print:
            return False, "Printer not ready."
        try:
            job = self._prepare_job(sbpl)
        except Exception as e:
            return False, f"Invalid print data: {e}"
        print_id = print_id or uuid.uuid4().hex
        self._print_sent = True
        self._print_started = False
        self._print_sent_at = time.monotonic()
        self._print_id = print_id
        self._print_has_rfid = b"\x1bIP0" in job
        self.can_print = False
        self.create_task(self._send_print(job, print_id))
        return True, print_id

    async def _send_print(self, job: bytes, print_id: str) -> None:
        if await self._send(job):
            self.emit_event("print_sent", print_id)
            return
        if self._print_id == print_id:
            self._reset_print_tracking()
        self.emit_event("print_sent_error", {"id": print_id, "error": "Failed to send print data."})

    def add_to_print_queue(self, sbpl: PrintData | list[PrintData]) -> str | list[str]:
        """Queue one or more jobs and return their unique IDs."""
        jobs = sbpl if isinstance(sbpl, list) else [sbpl]
        print_ids = []
        for item in jobs:
            print_id = uuid.uuid4().hex
            self._to_print.append((print_id, self._prepare_job(item)))
            print_ids.append(print_id)
        logging.info(f"{self.name} - Added to print queue. {len(self._to_print)} total.")
        return print_ids if isinstance(sbpl, list) else print_ids[0]

    def clear_print_queue(self) -> int:
        """Remove all queued jobs and return how many were dropped."""
        dropped = len(self._to_print)
        self._to_print.clear()
        return dropped

    @property
    def print_queue_size(self) -> int:
        return len(self._to_print)
