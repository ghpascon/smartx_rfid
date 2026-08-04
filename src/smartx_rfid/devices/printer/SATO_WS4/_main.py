import asyncio
import logging
from typing import Optional

from smartx_rfid.devices._base import DeviceBase
from .helpers import Helpers
from smartx_rfid.utils import get_hash


class SatoWs4Printer(DeviceBase, Helpers):
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

        self.is_connected = False
        self.can_print = False
        self.last_status = None
        self.last_can_print = False

        self._to_print: list[str] = []

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

    async def write(self, data: str, verbose=True):
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
            except Exception as e:
                logging.warning(f"[{self.name}] [SEND ERROR] data={data.strip()} error={e}")
                if self.is_connected:
                    self.is_connected = False

    def print(self, zpl: str):
        """Send ZPL command to printer."""
        if not self.is_connected:
            return False, "Printer not connected."
        if not self.can_print:
            return False, "Printer not ready."
        asyncio.create_task(self.write(zpl))
        self._print_sent = True
        self._zpl_id = get_hash(zpl)
        return True, self._zpl_id

    def add_to_print_queue(self, zpl: str | list[str]):
        """Add ZPL command to the print queue."""
        if isinstance(zpl, list):
            self._to_print = self._to_print + zpl
        else:
            self._to_print.append(zpl)
        logging.info(f"{self.name} - Added to print queue. {len(self._to_print)} total.")
