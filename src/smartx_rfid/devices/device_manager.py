import logging
import os
import json
from smartx_rfid.devices import (
    SERIAL,
    TCP,
    R700_IOT,
    X714,
    ACUPAD,
    SatoPrinter,
    SatoWs4Printer,
)
import asyncio
import tempfile
from typing import List, Dict, Optional, Tuple
from smartx_rfid.schemas.tag import WriteTagValidator
from smartx_rfid.schemas.devices import GpoSchema
from typing import Callable
import inspect
import threading


class DeviceManager:
    def __init__(self, devices_path: str, example_path: str = "", event_func: Callable | None = None):
        self.devices = []
        self._devices_path = devices_path
        self._example_path = example_path
        self._connect_tasks = []
        self._event_func: Callable | None = event_func
        # Protect concurrent access to `devices` and `_connect_tasks`
        self._lock = threading.RLock()
        # Async lock for coroutine-safe operations (created lazily)
        self._async_lock: Optional[asyncio.Lock] = None

    def __len__(self):
        return len(self.devices)

    def assign_event_function(self):
        # set event handlers
        if self._event_func is None:
            return
        for device in self.devices:
            device.on_event = self._event_func

    def load_devices(self):
        """Synchronous wrapper to load devices.

        If called outside an event loop this will run the async loader with
        `asyncio.run`. If called inside an event loop the async loader is
        scheduled and will run in background (prefer calling
        ``await _load_devices_async()`` from async code).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — run the async loader to completion
            asyncio.run(self._load_devices_async())
            return

        # If we're here, loop is running; schedule the async loader
        try:
            loop.create_task(self._load_devices_async())
        except Exception:
            # Fallback: run synchronously (may block the caller)
            asyncio.run(self._load_devices_async())

    async def _load_devices_async(self):
        """Actual async implementation for loading devices from disk.

        This method performs a preload cleanup, reads JSON device configs and
        instantiates device objects. It uses an asyncio lock to prevent
        concurrent loaders.
        """
        # Perform preload cleanup before acquiring the loader lock to avoid
        # deadlocks: cleanup will obtain the same async lock internally.
        try:
            await self._preload_cleanup_async()
        except Exception as e:
            logging.debug(f"Error during preload cleanup: {e}")

        lock = self._ensure_async_lock()
        async with lock:
            # Reset devices list and create directory if needed
            self.devices = []
            try:
                if not os.path.exists(self._devices_path):
                    os.makedirs(self._devices_path, exist_ok=True)
                    logging.info(f"📁 Directory created: {self._devices_path}")
            except Exception as e:
                logging.error(f"❌ Error checking/creating directory '{self._devices_path}': {e}")
                return

            # Iterate over JSON files in the directory
            for filename in os.listdir(self._devices_path):
                if filename.endswith(".json"):
                    filepath = os.path.join(self._devices_path, filename)
                    logging.info(f"📄 File: {filename}")
                    try:
                        # Read file in thread to avoid blocking
                        def _read():
                            with open(filepath, "r", encoding="utf-8") as f:
                                return json.load(f)

                        try:
                            data = await asyncio.to_thread(_read)
                        except Exception as e:
                            logging.error(f"❌ Error reading file '{filename}': {e}")
                            continue

                        # Lower case the keys
                        if isinstance(data, dict):
                            data = {k.lower(): v for k, v in data.items()}
                        else:
                            logging.error(f"❌ Invalid config in '{filename}', expected object")
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
                            continue

                        # If the device config is invalid, remove the file
                        if data.get("reader") is None:
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
                            continue

                        name = filename.replace(".json", "")
                        device_type = data.get("reader", "UNKNOWN")
                        # instantiate device (may be sync)
                        try:
                            self.add_device(name, device_type, data)
                        except Exception as e:
                            logging.error(f"❌ Error adding device '{name}': {e}")
                    except json.JSONDecodeError as e:
                        logging.error(f"❌ JSON decode error: {e}")
                    except Exception as e:
                        logging.error(f"❌ Error processing file '{filename}': {e}")

            # Assign event handlers to devices
            self.assign_event_function()

    def _ensure_async_lock(self) -> asyncio.Lock:
        """Create lazily and return an asyncio.Lock for coroutine-safe ops."""
        if getattr(self, "_async_lock", None) is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    async def _preload_cleanup_async(self):
        """Async cleanup run before reloading device configs.

        This method awaits the cancellation of connect tasks and disconnects
        devices using the async helpers. It's intended to be awaited from
        async callers. For synchronous callers use the `_preload_cleanup` wrapper.
        """
        try:
            await self.cancel_connect_tasks()
        except Exception as e:
            logging.debug(f"Error cancelling connect tasks during preload cleanup: {e}")

        try:
            await self.disconnect_devices()
        except Exception as e:
            logging.debug(f"Error disconnecting devices during preload cleanup: {e}")

    def _preload_cleanup(self):
        """Synchronous wrapper for preload cleanup.

        If called outside an event loop it will run the async cleanup to
        completion. If inside a running loop it will schedule the cleanup task
        to run in background.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._preload_cleanup_async())
            return

        # running loop: schedule background cleanup
        try:
            loop.create_task(self._preload_cleanup_async())
        except Exception:
            # fallback to running synchronously
            asyncio.run(self._preload_cleanup_async())

    def add_device(self, name: str, device_type: str, data: dict):
        device_type = device_type.upper()
        logging.info(f"🔍 Adding device: {name}")
        logging.info(f"📡 Reader type: {device_type}")

        ### SERIAL
        if device_type == "SERIAL":
            self.devices.append(SERIAL(name=name, **data))

        ### TCP
        elif device_type == "TCP":
            self.devices.append(TCP(name=name, **data))

        ### X714
        elif device_type == "X714":
            self.devices.append(X714(name=name, **data))

        ### R700
        elif device_type == "R700_IOT":
            self.devices.append(R700_IOT(name=name, **data))

        ### SATO
        elif device_type == "SATO":
            self.devices.append(SatoPrinter(name=name, **data))
        elif device_type == "SATO_WS4":
            self.devices.append(SatoWs4Printer(name=name, **data))

        ### ACUPAD
        elif device_type == "ACUPAD":
            self.devices.append(ACUPAD(name=name, **data))

        ###
        else:
            logging.warning(f"⚠️ Unknown reader type '{device_type}'. Device '{name}' was not added.")
            return  # Exit early if device is invalid

        logging.info(f"✅ Device '{name}' added successfully.")

    async def connect_devices(self, force: bool = False):
        """Start connection tasks for all devices.

        If connect tasks are already running and `force` is False, this is a no-op.
        When forcing, previous tasks will be cancelled and devices disconnected first.
        """
        # If there are active connect tasks and caller didn't request a force, skip.
        existing = [t for t in getattr(self, "_connect_tasks", []) if not t.done()]
        if existing and not force:
            logging.info("Connect tasks already running; skipping new connect.")
            return

        # Cancel previous tasks and ensure existing device connections are closed
        try:
            await self.cancel_connect_tasks()
        except Exception as e:
            logging.debug(f"Error cancelling previous connect tasks: {e}")

        try:
            await self.disconnect_devices()
        except Exception as e:
            logging.debug(f"Error disconnecting existing devices: {e}")

        # reload device definitions (async)
        await self._load_devices_async()

        tasks = []
        for device in self.devices:
            try:
                logging.info(f"🚀 Starting connection for device: '{device.name}'")
                # run device.connect inside a runner that ensures cleanup on cancel
                task = asyncio.create_task(self._device_connect_runner(device))
                tasks.append(task)
            except Exception as e:
                logging.error(f"❌ Error starting connection for device: '{device.name}': {e}")

        # keep tasks running in background; store handles for later cancellation
        self._connect_tasks = tasks
        if len(tasks) > 0:
            logging.info(f"Started {len(tasks)} device connect task(s).")

    async def cancel_connect_tasks(self):
        """Cancel any ongoing connect tasks and wait for their cancellation to complete.

        Snapshot the task list under the async lock, clear it and then perform
        cancellation/await outside the lock to avoid blocking other coroutines.
        """
        lock = self._ensure_async_lock()
        async with lock:
            tasks = list(getattr(self, "_connect_tasks", []) or [])
            self._connect_tasks = []

        if not tasks:
            return

        # request cancellation
        for t in tasks:
            try:
                if not t.done():
                    t.cancel()
                    logging.info("Cancelled previous device connection task.")
            except Exception:
                logging.debug("Error while cancelling a connect task", exc_info=True)

        # wait for them to finish/cancel
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            # exceptions may occur due to cancellations; log at debug
            logging.debug("Exceptions occurred while awaiting cancelled tasks", exc_info=True)

    async def _device_connect_runner(self, device):
        """Run device.connect() and ensure resources are closed on cancellation/exit."""
        try:
            connect = getattr(device, "connect", None)
            if not callable(connect):
                logging.warning(f"Device {getattr(device, 'name', None)} has no connect() method")
                return

            # If connect is async, await it; otherwise run it in a thread to avoid
            # blocking the event loop.
            if asyncio.iscoroutinefunction(connect) or inspect.iscoroutinefunction(connect):
                await connect()
            else:
                try:
                    await asyncio.to_thread(connect)
                except Exception as e:
                    logging.error(f"Error running blocking connect for device {getattr(device, 'name', None)}: {e}")
        except asyncio.CancelledError:
            logging.info(f"Connect task cancelled for device {getattr(device, 'name', None)}")
            raise
        except Exception as e:
            logging.error(f"Exception in connect runner for device {getattr(device, 'name', None)}: {e}")
        finally:
            # attempt to close any lingering resources on the device
            try:
                await self._close_device_resources(device)
            except Exception as e:
                logging.debug(f"Error during device resource cleanup for {getattr(device, 'name', None)}: {e}")

    async def _close_device_resources(self, device):
        """Try common close/disconnect methods on device; support sync and async methods."""
        for name in ("disconnect", "close", "stop", "shutdown"):
            method = getattr(device, name, None)
            if not callable(method):
                continue
            try:
                # If the method is async, await it. Otherwise run in thread to
                # avoid blocking the event loop for potentially slow shutdowns.
                if asyncio.iscoroutinefunction(method) or inspect.iscoroutinefunction(method):
                    await method()
                else:
                    try:
                        await asyncio.to_thread(method)
                    except Exception:
                        # If running in thread fails for some reason, try calling
                        # directly as a last resort.
                        try:
                            method()
                        except Exception as e:
                            logging.debug(f"Error calling {name} on device {getattr(device, 'name', None)}: {e}")
            except Exception as e:
                logging.debug(f"Error calling {name} on device {getattr(device, 'name', None)}: {e}")

    async def disconnect_devices(self):
        # Snapshot and clear device list under async lock to avoid races.
        lock = self._ensure_async_lock()
        async with lock:
            devices_snapshot = list(self.devices)
            self.devices = []

        for device in devices_snapshot:
            try:
                # cancel_all (sync or async)
                if hasattr(device, "cancel_all") and callable(getattr(device, "cancel_all")):
                    method = getattr(device, "cancel_all")
                    if asyncio.iscoroutinefunction(method) or inspect.iscoroutinefunction(method):
                        await method()
                    else:
                        await asyncio.to_thread(method)

                # shutdown (sync or async)
                if hasattr(device, "shutdown") and callable(getattr(device, "shutdown")):
                    method = getattr(device, "shutdown")
                    if asyncio.iscoroutinefunction(method) or inspect.iscoroutinefunction(method):
                        await method()
                    else:
                        await asyncio.to_thread(method)

            except Exception as e:
                logging.exception(f"Erro ao desconectar device {device}: {e}")
            finally:
                # Remove local reference
                try:
                    del device
                except Exception:
                    pass

    def get_devices(self):
        """Return a list of device names."""
        return [device.name for device in self.devices]

    def get_device_config(self, name: str):
        if name not in [device.name for device in self.devices]:
            return None
        try:
            with open(os.path.join(self._devices_path, f"{name}.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logging.error(f"❌ Error loading config for device '{name}': {e}")
            return None

    def get_device_types_example(self):
        """
        Return a list of example device names from the example path.
        Only JSON files are considered, and the '.json' extension is removed.
        The example_path should already point to the devices directory.
        """
        if not self._example_path:
            return []

        if not os.path.exists(self._example_path):
            return []

        return [f.replace(".json", "") for f in os.listdir(self._example_path) if f.endswith(".json")]

    def get_device_config_example(self, name: str):
        """
        Load and return the example configuration for a given device name.
        Returns None if the file does not exist or an error occurs.
        The example_path should already point to the devices directory.
        """
        if not self._example_path:
            return None

        filepath = os.path.join(self._example_path, f"{name}.json")

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logging.error(f"❌ Error loading example config for device '{name}': {e}")
            return None

    # ------------------------------------------------------------------
    # CRUD – device config files
    # ------------------------------------------------------------------

    async def create_device_config(self, name: str, data: dict, overwrite: bool = False) -> Tuple[bool, Optional[str]]:
        """Asynchronously persist a new device configuration and update memory.

        This performs an atomic write to disk, then attempts to update the in-
        memory device list without forcing a full reload. If a device with the
        same name is already loaded, it will try to shutdown that single
        device and replace it in-memory; if that fails, a full reload is
        performed as a fallback.
        """
        # Validate required 'reader' field
        normalized = {k.lower(): v for k, v in data.items()}
        if not normalized.get("reader"):
            return False, "Invalid config: 'reader' field is required."

        filepath = os.path.join(self._devices_path, f"{name}.json")

        if os.path.exists(filepath) and not overwrite:
            return (
                False,
                f"Device config '{name}' already exists. Use update_device_config to overwrite.",
            )

        # Perform atomic write in a thread to avoid blocking the event loop.
        def _atomic_write(devices_path, target_filepath, payload):
            os.makedirs(devices_path, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=f".{name}.", suffix=".json.tmp", dir=devices_path)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tf:
                    json.dump(payload, tf, indent=2, ensure_ascii=False)
                    tf.flush()
                    try:
                        os.fsync(tf.fileno())
                    except Exception:
                        pass
                os.replace(tmp_path, target_filepath)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

        try:
            await asyncio.to_thread(_atomic_write, self._devices_path, filepath, data)
            logging.info(f"✅ Device config '{name}' saved to '{filepath}'.")
        except Exception as e:
            logging.error(f"❌ Error writing device config '{name}': {e}")
            return False, str(e)

        # Post-write: try to update in-memory state without full reload.
        try:
            existing = self.get_device(name)
            if existing is not None:
                # Try graceful shutdown of the existing device. If shutdown
                # fails or the device remains, fallback to a full reload.
                try:
                    await self._shutdown_single_device(existing)
                except Exception as e:
                    logging.debug(f"Error shutting down existing device '{name}': {e}")
                    try:
                        await self._load_devices_async()
                    except Exception as e2:
                        logging.debug(f"Error reloading devices after failed shutdown: {e2}")
                    return True, None

                # If the device still exists after shutdown, perform full reload
                if self.get_device(name) is not None:
                    try:
                        await self._load_devices_async()
                    except Exception as e:
                        logging.debug(f"Error reloading devices after failed removal: {e}")
                    return True, None

                # Add the new device to memory and, if connect tasks are active,
                # start a connection task for it.
                lock = self._ensure_async_lock()
                async with lock:
                    try:
                        device_type = data.get("READER") or data.get("reader") or normalized.get("reader")
                        self.add_device(name, device_type, normalized)
                        self.assign_event_function()
                        existing_tasks = [t for t in getattr(self, "_connect_tasks", []) if not t.done()]
                        if existing_tasks:
                            new_device = self.get_device(name)
                            if new_device is not None:
                                task = asyncio.create_task(self._device_connect_runner(new_device))
                                self._connect_tasks.append(task)
                    except Exception as e:
                        logging.debug(f"Error adding new device to memory after create: {e}")
                        try:
                            await self._load_devices_async()
                        except Exception as e2:
                            logging.debug(f"Error reloading devices after failure adding new device: {e2}")
                return True, None

            # Not previously loaded: add to memory and start task if needed.
            lock = self._ensure_async_lock()
            async with lock:
                try:
                    device_type = data.get("READER") or data.get("reader") or normalized.get("reader")
                    self.add_device(name, device_type, normalized)
                    self.assign_event_function()
                    existing_tasks = [t for t in getattr(self, "_connect_tasks", []) if not t.done()]
                    if existing_tasks:
                        new_device = self.get_device(name)
                        if new_device is not None:
                            task = asyncio.create_task(self._device_connect_runner(new_device))
                            self._connect_tasks.append(task)
                except Exception as e:
                    logging.debug(f"Error adding new device in-memory after create: {e}")
                    try:
                        await self._load_devices_async()
                    except Exception as e2:
                        logging.debug(f"Error reloading devices after failure: {e2}")

            return True, None
        except Exception as e:
            logging.debug(f"Unexpected error during post-create handling: {e}")
            try:
                await self._load_devices_async()
            except Exception as e2:
                logging.debug(f"Error reloading devices after unexpected error: {e2}")
            return True, None

    async def update_device_config(self, name: str, data: dict) -> Tuple[bool, Optional[str]]:
        """
        Overwrite an existing device configuration and reload the device list.

        If the device is currently loaded (connected or not), it is gracefully
        shut down before the file is overwritten.  The device list is refreshed
        automatically after a successful write.

        Args:
            name: Logical device name whose config file will be replaced.
            data: New config dict; must contain a ``reader`` key.

        Returns:
            ``(True, None)`` on success, ``(False, error_message)`` otherwise.
        """
        # Use the async create implementation (overwrite) which will attempt
        # to shutdown the existing device and update memory without forcing a
        # full reload; it falls back to full reload on failure.
        ok, err = await self.create_device_config(name, data, overwrite=True)
        if not ok:
            return ok, err

        return True, None

    async def delete_device_config(self, name: str) -> Tuple[bool, Optional[str]]:
        """
        Remove a device configuration file from disk and reload the device list.

        If the device is currently loaded, it is gracefully shut down before the
        file is deleted.  The device list is refreshed automatically.

        Args:
            name: Logical device name to remove.

        Returns:
            ``(True, None)`` on success, ``(False, error_message)`` otherwise.
        """
        filepath = os.path.join(self._devices_path, f"{name}.json")

        if not os.path.exists(filepath):
            return False, f"Device config '{name}' not found."

        device = self.get_device(name)
        if device is not None:
            await self._shutdown_single_device(device)

        try:
            os.remove(filepath)
            logging.info(f"🗑️  Device config '{name}' deleted from '{filepath}'.")
        except Exception as e:
            logging.error(f"❌ Error deleting device config '{name}': {e}")
            return False, str(e)

        # Reload devices synchronously within this async context
        try:
            await self._load_devices_async()
        except Exception as e:
            logging.debug(f"Error reloading devices after delete: {e}")

        return True, None

    async def _shutdown_single_device(self, device) -> None:
        """
        Gracefully shut down a single device and remove it from the managed list.

        Calls ``cancel_all`` and ``shutdown`` when available, supporting both sync
        and async variants.  The device is then removed from ``self.devices``.
        """
        for method_name in ("cancel_all", "shutdown"):
            method = getattr(device, method_name, None)
            if not callable(method):
                continue
            try:
                if asyncio.iscoroutinefunction(method) or inspect.iscoroutinefunction(method):
                    await method()
                else:
                    await asyncio.to_thread(method)
            except Exception as e:
                logging.debug(f"Error calling {method_name} on device {getattr(device, 'name', None)}: {e}")

        # Remove device under async lock
        lock = self._ensure_async_lock()
        async with lock:
            try:
                self.devices.remove(device)
            except ValueError:
                pass

    def get_device_count(self):
        return len(self.devices)

    def get_device(self, name: str):
        return next((device for device in self.devices if device.name == name), None)

    def get_device_info(self, name: Optional[str] = None) -> List[Dict]:
        """
        Return device connection and reading status.

        If name is None, returns info for all devices.
        If name is provided, returns info for the specified device only.
        """
        if name is None:
            info_list = []
            for device in self.devices:
                info = self._get_single_device_info(device.name)
                if info:
                    info_list.append(info)
            return info_list

        info = self._get_single_device_info(name)
        return [info] if info else []

    def _get_single_device_info(self, name: str) -> Optional[Dict]:
        """
        Return information for a single device.
        """
        device = self.get_device(name)
        if not device:
            return None

        is_connected: bool = getattr(device, "is_connected", False)
        is_reading: bool = getattr(device, "is_reading", False) if is_connected else False
        is_gpi_trigger_on: bool = getattr(device, "is_gpi_trigger_on", False)
        device_type: str = getattr(device, "device_type", "UNKNOWN")
        can_print: bool = getattr(device, "can_print", False)
        to_print: int = len(getattr(device, "_to_print", []))
        has_serial, serial_number = self.get_serial_number(name)
        serial_number = serial_number if has_serial else "Unknown"
        device_class = device.__class__.__name__ if device else "Unknown"
        return {
            "name": device.name,
            "is_connected": is_connected,
            "is_reading": is_reading,
            "device_type": device_type,
            "is_gpi_trigger_on": is_gpi_trigger_on,
            "can_print": can_print,
            "to_print": to_print,
            "serial_number": serial_number,
            "device_class": device_class,
        }

    def any_device_reading(self) -> bool:
        """
        Check if any device is currently reading tags.
        """
        for device in self.devices:
            if getattr(device, "is_connected", False) and getattr(device, "is_reading", False):
                return True
        return False

    def _validate_device_for_inventory(self, name: str, check_gpi: bool = True) -> Tuple[bool, Optional[object]]:
        """
        Validate if a device can perform inventory operations.

        Args:
                name: Device name
                check_gpi: If True, also check if GPI trigger is on

        Returns:
                Tuple of (is_valid, device_object)
        """
        device = self.get_device(name)
        if not device:
            logging.warning(f"⚠️ Device '{name}' not found.")
            return False, None

        if not getattr(device, "device_type", None) == "rfid":
            logging.warning(f"⚠️ Device '{name}' is not an RFID device.")
            return False, None

        if not getattr(device, "is_connected", False):
            logging.warning(f"⚠️ Device '{name}' is not connected.")
            return False, None

        if check_gpi and getattr(device, "is_gpi_trigger_on", False):
            logging.warning(f"⚠️ Device '{name}' has GPI trigger on.")
            return False, None

        return True, device

    async def start_inventory(self, name: str) -> bool:
        """
        Start inventory on the specified device.

        Returns True if the command was sent successfully, False otherwise.
        """
        is_valid, device = self._validate_device_for_inventory(name, check_gpi=True)
        if not is_valid:
            return False

        try:
            await device.start_inventory()
            logging.info(f"✅ Starting inventory on device '{name}'.")
            return True
        except Exception as e:
            logging.error(f"❌ Error starting inventory on device '{name}': {e}")
            return False

    async def stop_inventory(self, name: str) -> bool:
        """
        Stop inventory on the specified device.

        Returns True if the command was sent successfully, False otherwise.
        """
        is_valid, device = self._validate_device_for_inventory(name)
        if not is_valid:
            return False

        try:
            await device.stop_inventory()
            logging.info(f"✅ Stopping inventory on device '{name}'.")
            return True
        except Exception as e:
            logging.error(f"❌ Error stopping inventory on device '{name}': {e}")
            return False

    async def start_inventory_all(self) -> Dict[str, bool]:
        """
        Start inventory on all connected RFID devices.

        Returns a dictionary with device names as keys and success status as values.
        """
        results = {}
        for device in self.devices:
            if device.device_type == "rfid" and device.is_connected:
                if not getattr(device, "is_gpi_trigger_on", False):
                    success = await self.start_inventory(device.name)
                    results[device.name] = success
                else:
                    logging.info(f"⚠️ Skipping device '{device.name}' (GPI trigger is on).")
                    results[device.name] = False
        return results

    async def stop_inventory_all(self) -> Dict[str, bool]:
        """
        Stop inventory on all connected RFID devices.

        Returns a dictionary with device names as keys and success status as values.
        """
        results = {}
        for device in self.devices:
            if device.device_type == "rfid" and device.is_connected:
                success = await self.stop_inventory(device.name)
                results[device.name] = success
        return results

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
            if asyncio.iscoroutinefunction(device.protected_inventory):
                await device.protected_inventory(active, password)
            else:
                device.protected_inventory(active, password)
            return True, None
        except Exception as e:
            return False, str(e)

    async def protected_mode(
        self, device_name: str, epc: str, password: str | None = None, active: bool = True
    ) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."

        if not getattr(device, "protected_mode", None):
            return False, f"Device '{device_name}' does not support protected mode."

        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."

        try:
            if asyncio.iscoroutinefunction(device.protected_mode):
                await device.protected_mode(epc, password, active)
            else:
                device.protected_mode(epc, password, active)
            return True, None
        except Exception as e:
            return False, str(e)

    def print(self, device_name: str, data: str) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."

        if not getattr(device, "device_type", "").lower() == "printer":
            return False, f"Device '{device_name}' is not a printer."

        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."

        try:
            return device.print(data)
        except Exception as e:
            return False, str(e)

    def add_to_print_queue(self, device_name: str, zpl: str | list[str]):
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
            logging.error(f"❌ Error adding to print queue on device '{device_name}': {e}")
            return False

    async def write_gpo(self, device_name: str, pin: int, state: bool, control: str = "static", time: int = 1000):
        # validate if device exists and supports GPO
        device = self.get_device(device_name)
        if device is None:
            return False, f"Device '{device_name}' not found."
        if not getattr(device, "write_gpo", None):
            return False, f"Device '{device_name}' does not support GPO control."
        # Check if device is connected
        if not getattr(device, "is_connected", False):
            return False, f"Device '{device_name}' is not connected."

        # Validate schema
        try:
            gpo_data = GpoSchema(pin=pin, state=state, control=control, time=time)
        except Exception as e:
            logging.error(f"❌ Invalid GPO data: {e}")
            return False, f"Invalid GPO data: {e}"

        # Attempt to write GPO
        try:
            if asyncio.iscoroutinefunction(device.write_gpo):
                await device.write_gpo(**gpo_data.model_dump())
            else:
                device.write_gpo(**gpo_data.model_dump())
            return True, None
        except Exception as e:
            logging.error(f"❌ Error writing GPO on device '{device_name}': {e}")
            return False, str(e)

    def get_serial_number(self, device_name: str) -> Tuple[bool, Optional[str]]:
        device = self.get_device(device_name)
        if device is None:
            return False, "Device not found."

        if not device.is_connected:
            return False, "Device is not connected."

        if not getattr(device, "serial_number", False):
            return False, "Device does not have a serial number."

        return True, getattr(device, "serial_number", None)
