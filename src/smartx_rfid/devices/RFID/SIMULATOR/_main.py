import asyncio
import logging
import random
from typing import Optional

from smartx_rfid.devices._base import DeviceBase


class SIMULATOR(DeviceBase):
    """Simple simulator device for testing RFID flows.

    Behavior:
    - Acts as an RFID reader (`device_type = "rfid").
    - Can be `connect()`ed; `start_inventory()` spawns a background
      task that emits `tag` events at `send_interval` seconds.
    - EPC and TID values increment by one on every emitted tag.
    """

    def __init__(
        self,
        name: str = "SIMULATOR",
        start_reading: bool = False,
        send_interval: float = 1.0,
        epc_start: str = "000000000000000000000001",
        tid_start: str = "e28000000000000000000001",
        epc_len: int = 24,
        tid_len: int = 24,
        gpi_start: bool = False,
        **kwargs,
    ):
        DeviceBase.__init__(self)

        # Basic identity
        self.name = name
        self.device_type = "rfid"

        # Behavioural flags
        self.start_reading = bool(start_reading)
        self.is_gpi_trigger_on = bool(gpi_start)

        # Runtime state
        self.is_connected = False
        self.is_reading = False
        self.serial_number: Optional[str] = None

        # Send parameters
        try:
            self.send_interval = float(send_interval)
        except Exception:
            self.send_interval = 1.0

        self._epc_len = int(epc_len)
        self._tid_len = int(tid_len)

        # Counters initialised from provided hex strings
        try:
            self._epc_counter = int(str(epc_start), 16)
        except Exception:
            self._epc_counter = 1
        try:
            self._tid_counter = int(str(tid_start), 16)
        except Exception:
            self._tid_counter = 0

        # Internal control
        self._send_task: Optional[asyncio.Task] = None
        self._stop_connection = False

        logging.info(f"{self.name} simulator ready (interval={self.send_interval}s)")

    def _fmt_hex(self, value: int, length: int) -> str:
        return format(value, "x").zfill(length).lower()

    async def connect(self):
        """Keep the simulated connection alive until cancelled."""
        self._stop_connection = False
        self._running = True
        try:
            self.is_connected = True

            # If configured to auto-start reading, do so
            if self.start_reading and not self.is_gpi_trigger_on:
                await self.start_inventory()

            # Keep the task alive until asked to stop or cancelled
            while not self._stop_connection:
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"{self.name} - Connect loop error: {e}")
        finally:
            # Best-effort cleanup
            try:
                await self.stop_inventory()
            except Exception:
                pass
            self.is_connected = False

    async def disconnect(self):
        self._stop_connection = True
        if self.is_reading:
            try:
                await self.stop_inventory()
            except Exception:
                pass
        self.is_connected = False

    async def close(self):
        self._stop_connection = True
        try:
            await self.disconnect()
        except Exception:
            pass
        await self.shutdown()

    async def start_inventory(self, check_gpi: bool = True) -> bool:
        """Begin emitting tag events periodically.

        Returns True on success, False on bad state (e.g., GPI or not connected).
        """
        if check_gpi and self.is_gpi_trigger_on:
            return False
        if not getattr(self, "is_connected", False):
            return False
        if getattr(self, "is_reading", False):
            return True

        # mark_reading_start via property setter
        self.is_reading = True

        # spawn background send loop
        self._send_task = self.create_task(self._send_tags_loop())
        return True

    async def stop_inventory(self, check_gpi: bool = True) -> bool:
        if not getattr(self, "is_reading", False):
            return True
        self.is_reading = False

        # wait a short while for the sender to exit
        if self._send_task is not None:
            try:
                await asyncio.wait_for(self._send_task, timeout=1.0)
            except Exception:
                pass
            self._send_task = None
        return True

    async def _send_tags_loop(self):
        while getattr(self, "is_reading", False) and self._running and getattr(self, "is_connected", False):
            epc = self._fmt_hex(self._epc_counter, self._epc_len)
            tid = self._fmt_hex(self._tid_counter, self._tid_len)
            rssi = -random.randint(30, 80)

            tag = {"epc": epc, "tid": tid, "ant": 1, "rssi": rssi}
            try:
                # Emit a tag event compatible with other devices
                self.emit_event("tag", tag)
            except Exception:
                logging.exception("Error emitting tag event")

            # increment for next tag
            self._epc_counter += 1
            self._tid_counter += 1

            try:
                await asyncio.sleep(self.send_interval)
            except asyncio.CancelledError:
                break

    # --- Minimal operational stubs used by DeviceManager ---
    async def write_epc(self, *args, **kwargs):
        logging.info(f"{self.name} - simulated write_epc: args={args} kwargs={kwargs}")
        return True

    async def protected_inventory(self, active: bool, password: str | None = None):
        self.is_protected_inventory_active = bool(active)
        return True, None

    async def protected_mode(self, epc: str, password: str | None = None, active: bool = True):
        return True, None

    async def write_gpo(
        self, pin: int = 1, state: bool = True, control: str = "static", time: int = 1000, *args, **kwargs
    ):
        try:
            self.emit_event("gpo", {"pin": pin, "state": state})
        except Exception:
            pass
        return True
