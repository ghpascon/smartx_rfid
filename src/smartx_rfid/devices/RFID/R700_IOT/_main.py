import asyncio
import logging

import httpx

from smartx_rfid.schemas.tag import WriteTagValidator
from smartx_rfid.utils.event import on_event

from .on_event import OnEvent
from .reader_helpers import ReaderHelpers
from .write_commands import WriteCommands
from .reader_config_example import R700_IOT_config_example


class R700_IOT(OnEvent, ReaderHelpers, WriteCommands):
    """Impinj R700 RFID reader using HTTP REST API."""

    def __init__(
        self,
        # READER CONFIG
        reading_config: dict,
        name: str = "R700",
        # CONNECTION
        ip: str = "192.168.1.101",  # Example hotsname: impinj-14-46-36
        username: str = "root",
        password: str = "impinj",
        start_reading: bool = False,
        # Firmware Version
        firmware_version: str = "8.4.1",
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
        self.name = name
        self.device_type = "rfid"

        self.ip = ip
        self.username = username
        self.password = password

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

        self.interface_config = {"rfidInterface": "rest"}
        self.auth = httpx.BasicAuth(self.username, self.password)

        self.tags_to_write = {}

        self.is_connected = False
        self.is_reading = False
        self._stop_connection = False

        self.firmware_version = firmware_version

        self.reading_config = reading_config
        self.config_example = R700_IOT_config_example

        self.on_event = on_event

    async def disconnect(self):
        """Safely disconnect from reader and stop reading."""
        """Desconecta o reader de forma segura."""
        logging.info(f"{self.name} 🔌 Disconnecting reader")
        self._stop_connection = True

        if self.is_reading:
            try:
                async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=5.0) as session:
                    await self.stop_inventory(session)
            except Exception as e:
                logging.warning(f"{self.name} ⚠️ Error stopping inventory during disconnect: {e}")

        self.is_connected = False
        self.is_reading = False
        self.on_event(self.name, "reading", False)
        self.on_event(self.name, "connection", False)

    async def connect(self):
        """Connect to R700 reader and start tag reading."""
        self._stop_connection = False
        while not self._stop_connection:
            async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0) as session:
                if self.is_connected:
                    self.on_event(self.name, "connection", False)

                self.is_connected = False
                self.is_reading = False

                # Configure interface
                success = await self.configure_interface(session)
                if not success:
                    logging.warning(f"{self.name} - Failed to configure interface")
                    await asyncio.sleep(1)
                    continue

                # Check firmware version
                success = await self.check_firmware_version(session)
                if not success:
                    logging.warning(
                        f"{self.name} - Incompatible firmware version. Update R700 firmware to {self.firmware_version}."
                    )
                    await asyncio.sleep(5)
                    continue

                # Stop any ongoing profiles
                success = await self.stop_inventory(session)
                if not success:
                    logging.warning(f"{self.name} - Failed to stop profiles")
                    await asyncio.sleep(1)
                    continue

                if self.start_reading or self.reading_config.get("startTriggers"):
                    success = await self.start_inventory(session)
                    if not success:
                        logging.warning(f"{self.name} - Failed to start inventory")
                        await asyncio.sleep(1)
                        continue
                if self.start_reading:
                    self.is_reading = True
                    self.on_event(self.name, "reading", True)

                # Clear GPO states
                for i in range(1, 4):
                    asyncio.create_task(self.write_gpo(pin=i, state=False))

                self.is_connected = True
                self.on_event(self.name, "connection", True)
                await self.get_tag_list(session)

    async def clear_tags(self):
        """Clear all stored tags from memory."""
        self.tags = {}

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
            async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0) as session:
                await self.post_to_reader(session, self.endpoint_gpo, payload=gpo_command, method="put")
        except Exception as e:
            logging.warning(f"{self.name} - Failed to set GPO: {e}")

    def write_epc(self, target_identifier: str | None, target_value: str | None, new_epc: str, password: str):
        """
        Write new EPC code to RFID tag.

        Args:
            target_identifier: How to find tag (epc, tid, user)
            target_value: Current tag value to match
            new_epc: New EPC code to write
            password: Tag access password
        """
        """
        Writes a new EPC (Electronic Product Code) to RFID tags.
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
            asyncio.create_task(self.send_write_command(validated_tag.model_dump()))
        except Exception as e:
            logging.warning(f"{self.name} - Write validation error: {e}")
