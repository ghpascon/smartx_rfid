import asyncio
import logging
import uuid
from typing import Optional

from smartx_rfid.devices._base import DeviceBase
from .helpers import Helpers


class SatoPrinter(DeviceBase, Helpers):
    def __init__(
        self,
        ip: str,
        name: str = "Sato",
        port: int = 9100,
        reconnection_time: int = 3,
        **kwargs,
    ):
        DeviceBase.__init__(self)
        self.name = name
        self.device_type = "printer"
        self.ip = ip
        self.port = port
        self.reconnection_time = reconnection_time
        self.is_connected: bool = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connect_lock = asyncio.Lock()
        self._running = True

        self.name = name

        self.ip = ip
        self.port = port

        self.reader = None
        self.writer = None

        self.can_print = False
        self.last_status = None

        self._to_print: list[tuple[str, str]] = []

        # Success on print
        self._print_sent = False
        self._zpl_id = None

    async def connect(self):
        """Connect to TCP server and keep connection alive."""
        while self._running:
            try:
                logging.info(f"Connecting: {self.name} - {self.ip}:{self.port}")
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=3
                )
                if not self.is_connected:
                    self.is_connected = True

                # Start the receive and monitor tasks
                tasks = [
                    self.create_task(self.receive_data()),
                    self.create_task(self.get_status()),
                ]

                # Wait until one of the tasks completes (e.g. disconnection)
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                # Cancel any remaining tasks
                for task in pending:
                    task.cancel()

                self.is_connected = False

            except Exception as e:
                if self.is_connected:
                    self.is_connected = False
                logging.error(f"[CONNECTION ERROR] {e}")

            await asyncio.sleep(3)

    async def close(self):
        # stop connect loop
        self._running = False

        # close writer if present
        try:
            if self.writer:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass
                self.writer = None
                self.reader = None
        except Exception:
            pass

        await self.shutdown()

    async def write(self, data: str, verbose=True) -> bool:
        """
        Send data through TCP connection.

        Args:
            data: Text to send
            verbose: Show sent data in logs
        """
        if self.is_connected and self.writer:
            try:
                to_send = (data + "\n").encode("utf-8")
                self.writer.write(to_send)
                await self.writer.drain()
                if verbose:
                    logging.info(f"[{self.name}] [SENT] {data.strip()}")
                return True
            except Exception as e:
                logging.warning(f"[{self.name}] [SEND ERROR] data={data.strip()} error={e}")
                if self.is_connected:
                    self.is_connected = False
        return False

    def print(self, zpl: str, print_id: str | None = None):
        """Send ZPL command to printer."""
        if not self.is_connected:
            return False, "Printer not connected."
        if not self.can_print:
            return False, "Printer not ready."
        print_id = print_id or uuid.uuid4().hex
        self._print_sent = True
        self._zpl_id = print_id
        asyncio.create_task(self._send_print(zpl, print_id))
        return True, print_id

    async def _send_print(self, zpl: str, print_id: str) -> None:
        if await self.write(zpl):
            self.emit_event("print_sent", print_id)
        else:
            if self._zpl_id == print_id:
                self._print_sent = False
                self._zpl_id = None
            self.emit_event("print_sent_error", {"id": print_id, "error": "Failed to send print data."})

    def add_to_print_queue(self, zpl: str | list[str]) -> str | list[str]:
        """Queue one or more ZPL jobs and return their unique IDs."""
        jobs = [zpl] if isinstance(zpl, str) else zpl
        print_ids = []
        for item in jobs:
            print_id = uuid.uuid4().hex
            self._to_print.append((print_id, item))
            print_ids.append(print_id)
        logging.info(f"{self.name} - Added to print queue. {len(self._to_print)} total.")
        return print_ids[0] if isinstance(zpl, str) else print_ids
