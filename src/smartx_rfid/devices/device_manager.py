import logging
import os
import json
from smartx_rfid.devices import SERIAL, TCP, R700_IOT, X714
import asyncio
from typing import List, Dict, Optional, Tuple
from smartx_rfid.schemas.tag import WriteTagValidator
from typing import Callable
import inspect


class DeviceManager:
    def __init__(self, devices_path: str, example_path: str = "", event_func: Callable | None = None):
        self.devices = []
        self._devices_path = devices_path
        self._example_path = example_path
        self._connect_tasks = []
        self._event_func: Callable | None = event_func

    def __len__(self):
        return len(self.devices)

    def assign_event_function(self):
        # set event handlers
        if self._event_func is None:
            logging.info("No event function provided; skipping assignment of event handlers.")
            return
        logging.info("Assigning event handlers to devices")
        for device in self.devices:
            device.on_event = self._event_func

    def load_devices(self):
        logging.info(f"Loading devices from: {self._devices_path}")
        self.devices = []

        try:
            # Create directory if it does not exist
            if not os.path.exists(self._devices_path):
                os.makedirs(self._devices_path)
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
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # If the device config is invalid, remove the file
                    if data.get("READER") is None:
                        os.remove(filepath)
                        continue
                    name = filename.replace(".json", "")
                    device_type = data.get("READER", "UNKNOWN")
                    self.add_device(name, device_type, data)
                except json.JSONDecodeError as e:
                    logging.error(f"❌ JSON decode error: {e}")
                except Exception as e:
                    logging.error(f"❌ Error processing file '{filename}': {e}")

        # Assign event handlers to devices
        self.assign_event_function()

    def add_device(self, name, device_type, data):
        logging.info(f"🔍 Adding device: {name}")
        logging.info(f"📡 Reader type: {device_type}")

        ### SERIAL
        if device_type == "SERIAL":
            self.devices.append(
                SERIAL(
                    name=name,
                    port=data.get("PORT", "AUTO"),
                    vid=data.get("VID", 1),
                    pid=data.get("PID", 1),
                    baudrate=data.get("BAUDRATE", 115200),
                )
            )

        ### TCP
        elif device_type == "TCP":
            self.devices.append(TCP(name=name, ip=data.get("IP"), port=data.get("PORT", 23)))

        ### X714
        elif device_type == "X714":
            self.devices.append(
                X714(
                    name=name,
                    connection_type=data.get("CONNECTION_TYPE", "SERIAL"),
                    port=data.get("PORT", "AUTO"),
                    baudrate=data.get("BAUDRATE", 115200),
                    vid=data.get("VID", 1),
                    pid=data.get("PID", 1),
                    ip=data.get("IP", "192.168.1.101"),
                    tcp_port=data.get("TCP_PORT", 23),
                    ble_name=data.get("BLE_NAME", "SMTX"),
                    buzzer=data.get("BUZZER", True),
                    session=data.get("SESSION", 1),
                    start_reading=data.get("START_READING", False),
                    gpi_start=data.get("GPI_START", False),
                    ant_dict=data.get("ANT_DICT", None),
                )
            )

        ### R700
        elif device_type == "R700_IOT":
            self.devices.append(
                R700_IOT(
                    name=name,
                    ip=data.get("IP"),
                    username=data.get("USERNAME", "root"),
                    password=data.get("PASSWORD", "impinj"),
                    start_reading=data.get("START_READING", True),
                    reading_config=data.get("READING_CONFIG", {}),
                )
            )

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
        logging.info(f"{'=' * 60}")
        logging.info("Connecting devices...")

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

        # reload device definitions
        self.load_devices()

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
        logging.info(f"Started {len(tasks)} device connect task(s).")

    async def cancel_connect_tasks(self):
        """Cancel any ongoing connect tasks and wait for their cancellation to complete."""
        tasks = list(getattr(self, "_connect_tasks", []) or [])
        if not tasks:
            self._connect_tasks = []
            return
        # request cancellation
        for t in tasks:
            if not t.done():
                t.cancel()
                logging.info("Cancelled previous device connection task.")
        # wait for them to finish/cancel
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            # exceptions are expected here due to cancellations; log at debug
            logging.debug("Exceptions occurred while awaiting cancelled tasks", exc_info=True)
        self._connect_tasks = []

    async def _device_connect_runner(self, device):
        """Run device.connect() and ensure resources are closed on cancellation/exit."""
        try:
            # if device.connect is a coroutine it will be awaited; if it raises CancelledError
            # it will propagate to here so we can cleanup in finally.
            res = device.connect()
            if asyncio.iscoroutine(res):
                await res
            else:
                # device.connect may be synchronous/blocking; run in thread
                try:
                    await asyncio.to_thread(res)
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
                res = method()
                if asyncio.iscoroutine(res):
                    await res
                # if method is sync, it should run immediately and close resource
            except Exception as e:
                logging.debug(f"Error calling {name} on device {getattr(device, 'name', None)}: {e}")

    async def disconnect_devices(self):
        for device in list(self.devices):
            try:
                # cancel_all (sync ou async)
                if hasattr(device, "cancel_all") and callable(getattr(device, "cancel_all")):
                    result = device.cancel_all()
                    if inspect.isawaitable(result):
                        await result

                # shutdown (sync ou async)
                if hasattr(device, "shutdown") and callable(getattr(device, "shutdown")):
                    result = device.shutdown()
                    if inspect.isawaitable(result):
                        await result

            except Exception as e:
                logging.exception(f"Erro ao desconectar device {device}: {e}")
            finally:
                # Remove da lista de controle
                try:
                    self.devices.remove(device)
                except ValueError:
                    pass

                # Remove referência local
                del device

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
        """
        if not self._example_path:
            return []

        # Join example path with 'devices' folder
        devices_path = os.path.join(self._example_path, "devices")

        if not os.path.exists(devices_path):
            return []

        return [f.replace(".json", "") for f in os.listdir(devices_path) if f.endswith(".json")]

    def get_device_config_example(self, name: str):
        """
        Load and return the example configuration for a given device name.
        Returns None if the file does not exist or an error occurs.
        """
        if not self._example_path:
            return None

        # Join example path with 'devices' folder
        devices_path = os.path.join(self._example_path, "devices")
        filepath = os.path.join(devices_path, f"{name}.json")

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logging.error(f"❌ Error loading example config for device '{name}': {e}")
            return None

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

        is_connected: bool = device.is_connected
        is_reading: bool = device.is_reading if is_connected else False
        is_gpi_trigger_on: bool = getattr(device, "is_gpi_trigger_on", False)
        return {
            "name": device.name,
            "is_connected": is_connected,
            "is_reading": is_reading,
            "device_type": device.device_type,
            "is_gpi_trigger_on": is_gpi_trigger_on,
        }

    def any_device_reading(self) -> bool:
        """
        Check if any device is currently reading tags.
        """
        for device in self.devices:
            if device.is_connected and device.is_reading:
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

        if not device.device_type == "rfid":
            logging.warning(f"⚠️ Device '{name}' is not an RFID device.")
            return False, None

        if not device.is_connected:
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

        try:
            await device.write_epc(**write_tag.model_dump())
            return True, None
        except Exception as e:
            return False, str(e)
