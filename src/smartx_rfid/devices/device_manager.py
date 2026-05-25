import logging
import os
import json
import asyncio
import tempfile
import inspect
from typing import List, Dict, Optional, Tuple, Callable

from smartx_rfid.devices import (
    SERIAL,
    TCP,
    R700_IOT,
    X714,
    ACUPAD,
    SatoPrinter,
    SatoWs4Printer,
)
from smartx_rfid.schemas.tag import WriteTagValidator
from smartx_rfid.schemas.devices import GpoSchema


_DEVICE_MAP = {
    "SERIAL": SERIAL,
    "TCP": TCP,
    "X714": X714,
    "R700_IOT": R700_IOT,
    "SATO": SatoPrinter,
    "SATO_WS4": SatoWs4Printer,
    "ACUPAD": ACUPAD,
}


class DeviceManager:
    def __init__(
        self,
        devices_path: str,
        example_path: str = "",
        event_func: Callable | None = None,
    ):
        self.devices: list = []
        self._devices_path = devices_path
        self._example_path = example_path
        self._event_func: Callable | None = event_func
        self._connect_tasks: list[asyncio.Task] = []
        # Single asyncio lock – created once, never replaced.
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assign_event_function(self) -> None:
        if self._event_func is None:
            return
        for device in self.devices:
            device.on_event = self._event_func

    @staticmethod
    async def _call_method(device, method_name: str) -> None:
        """Call a sync or async method on a device by name, if it exists."""
        method = getattr(device, method_name, None)
        if not callable(method):
            return
        try:
            if asyncio.iscoroutinefunction(method) or inspect.iscoroutinefunction(method):
                await method()
            else:
                await asyncio.to_thread(method)
        except Exception as e:
            logging.debug(f"Error calling '{method_name}' on device '{getattr(device, 'name', device)}': {e}")

    async def _shutdown_device(self, device) -> None:
        """Gracefully shut down one device and remove it from self.devices."""
        for method_name in ("cancel_all", "shutdown"):
            await self._call_method(device, method_name)

        async with self._lock:
            try:
                self.devices.remove(device)
            except ValueError:
                pass

    async def _cancel_connect_tasks(self) -> None:
        """Cancel all pending connect tasks and wait for them to finish."""
        async with self._lock:
            tasks, self._connect_tasks = self._connect_tasks, []

        if not tasks:
            return

        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _disconnect_all_devices(self) -> None:
        """Shut down every device currently in memory."""
        async with self._lock:
            snapshot, self.devices = self.devices, []

        for device in snapshot:
            for method_name in ("cancel_all", "shutdown"):
                await self._call_method(device, method_name)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load_devices_async(self) -> None:
        """
        Read JSON configs from disk and rebuild self.devices.

        NOTE: callers are responsible for cancelling connect tasks and
        disconnecting devices *before* calling this method, to avoid
        circular lock acquisition (this method acquires self._lock internally).
        """
        async with self._lock:
            self.devices = []

            if not os.path.exists(self._devices_path):
                try:
                    os.makedirs(self._devices_path, exist_ok=True)
                    logging.info(f"📁 Directory created: {self._devices_path}")
                except Exception as e:
                    logging.error(f"❌ Could not create directory '{self._devices_path}': {e}")
                    return

            for filename in os.listdir(self._devices_path):
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(self._devices_path, filename)
                name = filename[: -len(".json")]
                logging.info(f"📄 Loading: {filename}")

                try:
                    data = await asyncio.to_thread(self._read_json, filepath)
                except Exception as e:
                    logging.error(f"❌ Error reading '{filename}': {e}")
                    continue

                if data is None:
                    # _read_json already logged the error; remove corrupt file
                    self._safe_remove(filepath)
                    continue

                # Normalise keys to lower-case
                data = {k.lower(): v for k, v in data.items()}

                if not data.get("reader"):
                    logging.warning(f"⚠️ Missing 'reader' in '{filename}', removing.")
                    self._safe_remove(filepath)
                    continue

                try:
                    self._add_device(name, data["reader"], data)
                except Exception as e:
                    logging.error(f"❌ Error adding device '{name}': {e}")

            self._assign_event_function()

    @staticmethod
    def _read_json(filepath: str) -> Optional[dict]:
        """Read and parse a JSON file; return None on error."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logging.error(f"❌ '{filepath}' does not contain a JSON object.")
                return None
            return data
        except json.JSONDecodeError as e:
            logging.error(f"❌ JSON decode error in '{filepath}': {e}")
            return None
        except Exception as e:
            logging.error(f"❌ Could not read '{filepath}': {e}")
            return None

    @staticmethod
    def _safe_remove(filepath: str) -> None:
        try:
            os.remove(filepath)
        except Exception:
            pass

    def _add_device(self, name: str, device_type: str, data: dict) -> None:
        """Instantiate and append a device. Raises on unknown type."""
        key = device_type.upper()
        cls = _DEVICE_MAP.get(key)
        if cls is None:
            logging.warning(f"⚠️ Unknown reader type '{device_type}'. Device '{name}' not added.")
            return

        logging.info(f"🔍 Adding device '{name}' (type={key})")
        self.devices.append(cls(name=name, **data))
        logging.info(f"✅ Device '{name}' added.")

    # ------------------------------------------------------------------
    # Public API – lifecycle
    # ------------------------------------------------------------------

    async def connect_devices(self, force: bool = False) -> None:
        """Start connection tasks for all devices.

        If tasks are already running and *force* is False, this is a no-op.
        Set force=True to tear everything down and reconnect from scratch.
        """
        active = [t for t in self._connect_tasks if not t.done()]
        if active and not force:
            logging.info("Connect tasks already running; skipping.")
            return

        # Full teardown before reload
        await self._cancel_connect_tasks()
        await self._disconnect_all_devices()
        await self._load_devices_async()

        tasks = []
        for device in self.devices:
            logging.info(f"🚀 Starting connection for '{device.name}'")
            task = asyncio.create_task(self._device_connect_runner(device))
            tasks.append(task)

        self._connect_tasks = tasks
        if tasks:
            logging.info(f"Started {len(tasks)} connect task(s).")

    async def _device_connect_runner(self, device) -> None:
        """Run device.connect() and clean up resources on exit/cancellation."""
        try:
            connect = getattr(device, "connect", None)
            if not callable(connect):
                logging.warning(f"Device '{getattr(device, 'name', device)}' has no connect().")
                return

            if asyncio.iscoroutinefunction(connect) or inspect.iscoroutinefunction(connect):
                await connect()
            else:
                await asyncio.to_thread(connect)

        except asyncio.CancelledError:
            logging.info(f"Connect task cancelled for '{getattr(device, 'name', device)}'.")
            raise
        except Exception as e:
            logging.error(f"Exception in connect runner for '{getattr(device, 'name', device)}': {e}")
        finally:
            for method_name in ("disconnect", "close", "stop", "shutdown"):
                await self._call_method(device, method_name)

    # ------------------------------------------------------------------
    # Public API – queries
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.devices)

    def get_device_count(self) -> int:
        return len(self.devices)

    def get_devices(self) -> List[str]:
        return [d.name for d in self.devices]

    def get_device(self, name: str):
        return next((d for d in self.devices if d.name == name), None)

    def get_device_config(self, name: str) -> Optional[dict]:
        filepath = os.path.join(self._devices_path, f"{name}.json")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            logging.error(f"❌ Error loading config for '{name}': {e}")
            return None

    def get_device_types_example(self) -> List[str]:
        if not self._example_path or not os.path.exists(self._example_path):
            return []
        return [f[: -len(".json")] for f in os.listdir(self._example_path) if f.endswith(".json")]

    def get_device_config_example(self, name: str) -> Optional[dict]:
        if not self._example_path:
            return None
        filepath = os.path.join(self._example_path, f"{name}.json")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            logging.error(f"❌ Error loading example config for '{name}': {e}")
            return None

    def get_device_info(self, name: Optional[str] = None) -> List[Dict]:
        if name is not None:
            info = self._get_single_device_info(name)
            return [info] if info else []
        return [info for d in self.devices if (info := self._get_single_device_info(d.name))]

    def _get_single_device_info(self, name: str) -> Optional[Dict]:
        device = self.get_device(name)
        if not device:
            return None

        is_connected: bool = getattr(device, "is_connected", False)
        has_serial, serial_number = self.get_serial_number(name)
        return {
            "name": device.name,
            "is_connected": is_connected,
            "is_reading": getattr(device, "is_reading", False) if is_connected else False,
            "device_type": getattr(device, "device_type", "UNKNOWN"),
            "is_gpi_trigger_on": getattr(device, "is_gpi_trigger_on", False),
            "can_print": getattr(device, "can_print", False),
            "to_print": len(getattr(device, "_to_print", [])),
            "serial_number": serial_number if has_serial else "Unknown",
            "device_class": device.__class__.__name__,
        }

    def any_device_reading(self) -> bool:
        return any(getattr(d, "is_connected", False) and getattr(d, "is_reading", False) for d in self.devices)

    # ------------------------------------------------------------------
    # CRUD – device config files
    # ------------------------------------------------------------------

    async def create_device_config(self, name: str, data: dict, overwrite: bool = False) -> Tuple[bool, Optional[str]]:
        """Persist a new device configuration and update the in-memory list.

        The file is written atomically. Afterwards the relevant device is
        restarted in-memory without triggering a full reload of all devices.
        Falls back to a full reload only if the targeted partial update fails.
        """
        # Normalise once; use this everywhere for consistency
        normalised = {k.lower(): v for k, v in data.items()}

        if not normalised.get("reader"):
            return False, "Invalid config: 'reader' field is required."

        filepath = os.path.join(self._devices_path, f"{name}.json")

        if os.path.exists(filepath) and not overwrite:
            return (
                False,
                f"Device config '{name}' already exists. Use update_device_config to overwrite.",
            )

        # Atomic write (normalised data goes to disk too, avoiding drift)
        try:
            await asyncio.to_thread(self._atomic_write, filepath, normalised)
            logging.info(f"✅ Device config '{name}' saved to '{filepath}'.")
        except Exception as e:
            logging.error(f"❌ Error writing device config '{name}': {e}")
            return False, str(e)

        # Update in-memory state for this single device
        try:
            await self._reload_single_device(name, normalised)
        except Exception as e:
            logging.warning(f"⚠️ Partial reload failed for '{name}', doing full reload: {e}")
            try:
                await self._load_devices_async()
            except Exception as e2:
                logging.error(f"❌ Full reload also failed: {e2}")

        return True, None

    async def update_device_config(self, name: str, data: dict) -> Tuple[bool, Optional[str]]:
        """Overwrite an existing device configuration and reload the device."""
        return await self.create_device_config(name, data, overwrite=True)

    async def delete_device_config(self, name: str) -> Tuple[bool, Optional[str]]:
        """Remove a device config file from disk and remove it from memory."""
        filepath = os.path.join(self._devices_path, f"{name}.json")

        if not os.path.exists(filepath):
            return False, f"Device config '{name}' not found."

        device = self.get_device(name)
        if device is not None:
            await self._shutdown_device(device)

        try:
            os.remove(filepath)
            logging.info(f"🗑️  Device config '{name}' deleted.")
        except Exception as e:
            logging.error(f"❌ Error deleting device config '{name}': {e}")
            return False, str(e)

        return True, None

    async def _reload_single_device(self, name: str, normalised: dict) -> None:
        """Shut down the named device (if loaded) and re-add it from normalised config."""
        device = self.get_device(name)
        if device is not None:
            await self._shutdown_device(device)

        async with self._lock:
            self._add_device(name, normalised["reader"], normalised)
            self._assign_event_function()

            # If connection tasks are active, start one for the new device too
            active_tasks = [t for t in self._connect_tasks if not t.done()]
            if active_tasks:
                new_device = self.get_device(name)
                if new_device is not None:
                    task = asyncio.create_task(self._device_connect_runner(new_device))
                    self._connect_tasks.append(task)

    def _atomic_write(self, filepath: str, payload: dict) -> None:
        """Write *payload* to *filepath* atomically using a temp file + rename."""
        directory = os.path.dirname(filepath)
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp.", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, filepath)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # RFID inventory
    # ------------------------------------------------------------------

    def _validate_rfid_device(self, name: str, check_gpi: bool = True) -> Tuple[bool, Optional[object]]:
        device = self.get_device(name)
        if device is None:
            logging.warning(f"⚠️ Device '{name}' not found.")
            return False, None
        if getattr(device, "device_type", None) != "rfid":
            logging.warning(f"⚠️ Device '{name}' is not an RFID device.")
            return False, None
        if not getattr(device, "is_connected", False):
            logging.warning(f"⚠️ Device '{name}' is not connected.")
            return False, None
        if check_gpi and getattr(device, "is_gpi_trigger_on", False):
            logging.warning(f"⚠️ Device '{name}' has GPI trigger active.")
            return False, None
        return True, device

    async def start_inventory(self, name: str) -> bool:
        valid, device = self._validate_rfid_device(name, check_gpi=True)
        if not valid:
            return False
        try:
            await device.start_inventory()
            logging.info(f"✅ Inventory started on '{name}'.")
            return True
        except Exception as e:
            logging.error(f"❌ Error starting inventory on '{name}': {e}")
            return False

    async def stop_inventory(self, name: str) -> bool:
        valid, device = self._validate_rfid_device(name, check_gpi=False)
        if not valid:
            return False
        try:
            await device.stop_inventory()
            logging.info(f"✅ Inventory stopped on '{name}'.")
            return True
        except Exception as e:
            logging.error(f"❌ Error stopping inventory on '{name}': {e}")
            return False

    async def start_inventory_all(self) -> Dict[str, bool]:
        results = {}
        for device in self.devices:
            if device.device_type == "rfid" and device.is_connected:
                if not getattr(device, "is_gpi_trigger_on", False):
                    results[device.name] = await self.start_inventory(device.name)
                else:
                    logging.info(f"⚠️ Skipping '{device.name}' (GPI trigger active).")
                    results[device.name] = False
        return results

    async def stop_inventory_all(self) -> Dict[str, bool]:
        results = {}
        for device in self.devices:
            if device.device_type == "rfid" and device.is_connected:
                results[device.name] = await self.stop_inventory(device.name)
        return results

    # ------------------------------------------------------------------
    # EPC write / protected mode
    # ------------------------------------------------------------------

    async def write_epc(self, device_name: str, write_tag: WriteTagValidator) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if not getattr(device, "write_epc", None):
            return False, f"Device '{device_name}' does not support writing EPC."
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."
        try:
            await device.write_epc(**write_tag.model_dump())
            return True, None
        except Exception as e:
            return False, str(e)

    async def protected_inventory(
        self, device_name: str, active: bool, password: str | None = None
    ) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if not getattr(device, "protected_inventory", None):
            return False, f"Device '{device_name}' does not support protected inventory."
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."
        try:
            await self._call_or_run(device.protected_inventory, active, password)
            return True, None
        except Exception as e:
            return False, str(e)

    async def protected_mode(
        self,
        device_name: str,
        epc: str,
        password: str | None = None,
        active: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if not getattr(device, "protected_mode", None):
            return False, f"Device '{device_name}' does not support protected mode."
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."
        try:
            await self._call_or_run(device.protected_mode, epc, password, active)
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def _call_or_run(func, *args):
        """Await func if async, otherwise run it in a thread."""
        if asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func):
            await func(*args)
        else:
            await asyncio.to_thread(func, *args)

    # ------------------------------------------------------------------
    # GPO
    # ------------------------------------------------------------------

    async def write_gpo(
        self,
        device_name: str,
        pin: int,
        state: bool,
        control: str = "static",
        time: int = 1000,
    ) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if not getattr(device, "write_gpo", None):
            return False, f"Device '{device_name}' does not support GPO."
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."

        try:
            gpo_data = GpoSchema(pin=pin, state=state, control=control, time=time)
        except Exception as e:
            return False, f"Invalid GPO data: {e}"

        try:
            await self._call_or_run(device.write_gpo, **gpo_data.model_dump())
            return True, None
        except Exception as e:
            logging.error(f"❌ Error writing GPO on '{device_name}': {e}")
            return False, str(e)

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    def print(self, device_name: str, data: str) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if getattr(device, "device_type", "").lower() != "printer":
            return False, f"Device '{device_name}' is not a printer."
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."
        try:
            return device.print(data)
        except Exception as e:
            return False, str(e)

    def add_to_print_queue(self, device_name: str, zpl: str | list[str]) -> bool:
        device = self.get_device(device_name)
        if device is None:
            logging.error(f"❌ Device '{device_name}' not found.")
            return False
        if not getattr(device, "add_to_print_queue", None):
            logging.error(f"❌ Device '{device_name}' does not support print queue.")
            return False
        if not getattr(device, "is_connected", False):
            logging.error(f"❌ Device '{device_name}' is not connected.")
            return False
        try:
            device.add_to_print_queue(zpl)
            return True
        except Exception as e:
            logging.error(f"❌ Error adding to print queue on '{device_name}': {e}")
            return False

    # ------------------------------------------------------------------
    # Serial number
    # ------------------------------------------------------------------

    def get_serial_number(self, device_name: str) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, "Device not found."
        if not getattr(device, "is_connected", False):
            return False, "Device is not connected."
        serial = getattr(device, "serial_number", None)
        if not serial:
            return False, "Device does not have a serial number."
        return True, serial
