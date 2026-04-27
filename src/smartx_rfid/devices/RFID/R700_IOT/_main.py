import asyncio
import logging

import httpx

from smartx_rfid.schemas.tag import WriteTagValidator
from smartx_rfid.utils.event import on_event
from smartx_rfid.utils import regex_hex

from .on_event import OnEvent
from .reader_helpers import ReaderHelpers
from .write_commands import WriteCommands
from .reader_config_example import R700_IOT_config_example, ant_config_example


from smartx_rfid.devices._base import DeviceBase


class R700_IOT(DeviceBase, OnEvent, ReaderHelpers, WriteCommands):
    """Impinj R700 RFID reader using HTTP REST API."""

    def __init__(
        self,
        # READER CONFIG
        name: str = "R700",
        reading_config: dict | None = None,
        # CONNECTION
        ip: str = "192.168.1.101",  # Example hotsname: impinj-14-46-36
        username: str = "root",
        password: str = "impinj",
        start_reading: bool = False,
        # Firmware Version
        firmware_version: str | None = None,
        session: int = 1,
        active_ant: list[int] = [1],
        read_power: int = 3000,
        read_rssi: int = -80,
        search_mode: str = "single-target",
        rf_mode: int = 4,
        gpi_start: bool = False,
        protected_inventory_active: bool = False,
        protected_inventory_password: str | None = "12345678",
        **kwargs,
    ):
        """
        Create R700 RFID reader.

        Args:
            reading_config: Configuration for tag reading
            name: Device name
            ip: IP address of reader
            username: Login username
            password: Login password
            start_reading: Start reading tags automatically
            firmware_version: Expected firmware version
        """
        # READER CONFIG
        self.config_example = R700_IOT_config_example
        self.is_protected_inventory_active = protected_inventory_active
        if reading_config is None:
            # Validation
            if session not in [0, 1, 2, 3]:
                session = 1
            if not isinstance(read_power, int):
                read_power = 3000
            if read_power < 1000:
                read_power = read_power * 100
            if read_power < 1000 or read_power > 3300:
                read_power = 3000
            if not isinstance(read_rssi, int):
                read_rssi = -80
            if not isinstance(search_mode, str):
                search_mode = "single-target"
            if search_mode not in ["single-target", "dual-target"]:
                search_mode = "single-target"
            if not isinstance(rf_mode, int):
                rf_mode = 4
            if not isinstance(protected_inventory_active, bool):
                protected_inventory_active = False
            if not regex_hex(str(protected_inventory_password), 8):
                protected_inventory_active = False
                protected_inventory_password = "12345678"
            # Configuration
            reading_config = R700_IOT_config_example.copy()
            if gpi_start is False:
                reading_config.pop("startTriggers")
                reading_config.pop("stopTriggers")
            reading_config["antennaConfigs"] = []
            # Antennas
            if not isinstance(active_ant, list):
                active_ant = [1]
            for ant in active_ant:
                ant_cfg = ant_config_example.copy()
                ant_cfg["antennaPort"] = ant
                ant_cfg["inventorySession"] = session
                ant_cfg["receiveSensitivityDbm"] = read_rssi
                ant_cfg["transmitPowerCdbm"] = read_power
                ant_cfg["protectedModePinHex"] = protected_inventory_password
                ant_cfg["inventorySearchMode"] = search_mode
                ant_cfg["rfMode"] = rf_mode
                if not protected_inventory_active:
                    ant_cfg.pop("protectedModePinHex")
                reading_config["antennaConfigs"].append(ant_cfg)

        self.reading_config = reading_config

        self.protected_inventory_password = protected_inventory_password
        # Name
        if not isinstance(name, str):
            name = "R700"
            logging.warning("Invalid name provided. Using default name 'R700'.")
        self.name = name
        self.device_type = "rfid"

        self.ip = ip

        # Access
        if not isinstance(username, str):
            username = "root"
        if not isinstance(password, str):
            password = "impinj"
        self.username = username
        self.password = password

        if not isinstance(start_reading, bool):
            start_reading = False
        self.start_reading = start_reading

        # URL AND ENDPOINTS
        self.urlBase = f"https://{self.ip}/api/v1"
        self.endpoint_interface = f"{self.urlBase}/system/rfid/interface"
        self.check_version_endpoint = f"{self.urlBase}/system/image"
        self.endpoint_start = f"{self.urlBase}/profiles/inventory/start"
        self.endpoint_stop = f"{self.urlBase}/profiles/stop"
        self.endpointDataStream = f"{self.urlBase}/data/stream"
        self.endpoint_gpo = f"{self.urlBase}/device/gpos"
        self.endpoint_write = f"{self.urlBase}/profiles/inventory/tag-access"
        self.endpoint_status = f"{self.urlBase}/status"
        self.endpoint_info = f"{self.urlBase}/system"

        self.interface_config = {"rfidInterface": "rest"}
        self.auth = httpx.BasicAuth(self.username, self.password)

        self.tags_to_write = {}

        self.is_connected = False
        self.is_reading = False
        self._stop_connection = False
        self._command_lock = asyncio.Lock()  # Lock para evitar comandos concorrentes
        self._session: httpx.AsyncClient | None = None  # Sessão HTTP reutilizável

        if not isinstance(firmware_version, str):
            firmware_version = None
        self.firmware_version = firmware_version

        self.on_event = on_event

        DeviceBase.__init__(self)

        self.is_connected = False
        self.is_reading = False
        self.serial_number = None
        self.is_gpi_trigger_on = "startTriggers" in self.reading_config or "stopTriggers" in self.reading_config
        if self.is_gpi_trigger_on:
            self.start_reading = False

        logging.info(f"{self.name} initialized with config: {self.reading_config}")

    async def disconnect(self):
        """Safely disconnect from reader and stop reading."""
        logging.info(f"{self.name} 🔌 Disconnecting reader")
        self._stop_connection = True

        if self.is_reading:
            try:
                async with self._command_lock:
                    if self._session is not None:
                        await self._stop_inventory(self._session)
                    else:
                        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0) as session:
                            await self._stop_inventory(session)
            except Exception as e:
                logging.warning(f"{self.name} ⚠️ Error stopping inventory during disconnect: {e}")

        # Fechar sessão HTTP
        if self._session is not None:
            await self._session.aclose()
            self._session = None

        self.is_connected = False
        self.is_reading = False
        self.on_event(self.name, "reading", False)
        self.on_event(self.name, "connection", False)
        self.serial_number = None

    async def close(self):
        """Graceful shutdown for R700: stop stream and cancel background tasks."""
        # set stop flag and call disconnect to close session and stop inventory
        self._stop_connection = True
        try:
            await self.disconnect()
        except Exception:
            pass

        await self.shutdown()

    async def connect(self):
        """Connect to R700 reader and start tag reading."""
        self._stop_connection = False
        while not self._stop_connection:
            try:
                # Criar sessão HTTP persistente
                self._session = httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0)

                if self.is_connected:
                    self.on_event(self.name, "connection", False)

                self.is_connected = False
                self.is_reading = False

                # Configure interface
                async with self._command_lock:
                    success = await self.configure_interface(self._session)
                    if not success:
                        logging.warning(f"{self.name} - Failed to configure interface")
                        await self._session.aclose()
                        self._session = None
                        await asyncio.sleep(1)
                        continue

                # Check firmware version
                success = await self.check_firmware_version(self._session)
                if not success:
                    logging.warning(
                        f"{self.name} - Incompatible firmware version. Update R700 firmware to {self.firmware_version}."
                    )
                    await self._session.aclose()
                    self._session = None
                    await asyncio.sleep(5)
                    continue

                # Stop any ongoing profiles
                async with self._command_lock:
                    success = await self._stop_inventory(self._session)
                    if not success:
                        logging.warning(f"{self.name} - Failed to stop profiles")
                        await self._session.aclose()
                        self._session = None
                        await asyncio.sleep(1)

                # Get reader info to retrieve serial number
                await self.get_reader_info()

                # Start inventory if needed
                if self.start_reading or self.is_gpi_trigger_on:
                    async with self._command_lock:
                        success = await self._start_inventory(self._session)
                        if not success:
                            logging.warning(f"{self.name} - Failed to start inventory")
                            await self._session.aclose()
                            self._session = None
                            await asyncio.sleep(1)
                            continue
                if self.start_reading:
                    self.is_reading = True
                    self.on_event(self.name, "reading", True)

                # Clear GPO states
                for i in range(1, 4):
                    if hasattr(self, "create_task"):
                        self.create_task(self.write_gpo(pin=i, state=False))
                    else:
                        asyncio.create_task(self.write_gpo(pin=i, state=False))

                self.is_connected = True
                self.on_event(self.name, "connection", True)

                # Manter conexão com stream de dados
                await self.get_tag_list(self._session)

            except Exception as e:
                logging.error(f"{self.name} - Connection error: {e}")
                if self._session is not None:
                    await self._session.aclose()
                    self._session = None
                self.is_connected = False
                self.on_event(self.name, "connection", False)
                self.serial_number = None
                await asyncio.sleep(2)

    async def write_gpo(
        self,
        pin: int = 1,
        state: bool | str = True,
        control: str = "static",
        time: int = 1000,
        *args,
        **kwargs,
    ):
        """
        Control GPO (output) pins on reader.

        Args:
            pin: GPO pin number
            state: Turn pin on (True) or off (False)
            control: Control type (static or pulse)
            time: Pulse duration in milliseconds
        """
        gpo_command = await self.get_gpo_command(pin=pin, state=state, control=control, time=time)
        try:
            async with self._command_lock:
                if self._session is not None and not self._session.is_closed:
                    await self.post_to_reader(self._session, self.endpoint_gpo, payload=gpo_command, method="put")
                else:
                    async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0) as session:
                        await self.post_to_reader(session, self.endpoint_gpo, payload=gpo_command, method="put")
        except Exception as e:
            logging.warning(f"{self.name} - Failed to set GPO: {e}")

    async def write_epc(self, target_identifier: str | None, target_value: str | None, new_epc: str, password: str):
        """
        Write new EPC code to RFID tag.

        Args:
            target_identifier: How to find tag (epc, tid, user)
            target_value: Current tag value to match
            new_epc: New EPC code to write
            password: Tag access password
        """
        try:
            validated_tag = WriteTagValidator(
                target_identifier=target_identifier,
                target_value=target_value,
                new_epc=new_epc,
                password=password,
            )
            logging.info(
                f"{self.name} - Writing EPC: {validated_tag.new_epc} (Current: {validated_tag.target_identifier}={validated_tag.target_value})"
            )
            cmd = self.get_write_cmd(validated_tag)
            await self.send_write_command(cmd)
        except Exception as e:
            logging.warning(f"{self.name} - Write validation error: {e}")

    async def protected_inventory(self, active: bool, password: str = None, restart_inventory: bool = True):
        if password is None:
            password = self.protected_inventory_password

        if not regex_hex(str(password), 8):
            return False, "Error: Invalid password format"

        antennas = self.reading_config.get("antennaConfigs")
        for ant in antennas:
            if active:
                ant["protectedModePinHex"] = password
            else:
                ant.pop("protectedModePinHex", None)

        if restart_inventory:
            await self.stop_inventory(check_gpi=False)
            await self.start_inventory(check_gpi=False)

        self.is_protected_inventory_active = active
        return True, None
