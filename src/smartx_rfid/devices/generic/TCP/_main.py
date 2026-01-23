import asyncio
import logging

from .helpers import Helpers
from smartx_rfid.utils.event import on_event
from typing import Callable
from smartx_rfid.devices._base import DeviceBase


class TCP(DeviceBase, Helpers):
    """TCP connection handler for network communication."""

    def __init__(
        self,
        name: str = "GENERIC_TCP",
        ip: str = "192.168.1.101",
        port: int = 23,
    ):
        """
        Create TCP connection.

        Args:
            name: Device name
            ip: IP address to connect
            port: TCP port number
        """
        DeviceBase.__init__(self)
        self.name = name
        self.device_type = "generic"

        self.ip = ip
        self.port = port

        self.reader = None
        self.writer = None

        self.is_connected = False
        self.on_event: Callable = on_event

    async def connect(self):
        """Connect to TCP server and keep connection alive."""
        while self._running:
            try:
                logging.info(f"Connecting: {self.name} - {self.ip}:{self.port}")
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=3
                )
                self.is_connected = True
                self.on_event(self.name, "connection", True)

                # Start the receive and monitor tasks
                tasks = [
                    self.create_task(self.receive_data()),
                    self.create_task(self.monitor_connection()),
                ]

                # Wait until one of the tasks completes (e.g. disconnection)
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                # Cancel any remaining tasks
                for task in pending:
                    task.cancel()

                self.is_connected = False
                self.on_event(self.name, "connection", False)

            except Exception as e:
                self.is_connected = False
                self.on_event(self.name, "connection", False)
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
                data = data + "\n"
                self.writer.write(data.encode())
                await self.writer.drain()
                if verbose:
                    logging.info(f"[SENT] {data.strip()}")
            except Exception as e:
                logging.warning(f"[SEND ERROR] {e}")
                self.is_connected = False
                self.on_event(self.name, "connection", False)
