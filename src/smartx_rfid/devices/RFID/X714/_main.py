import asyncio
import logging

from typing import Callable

from .ble_protocol import BLEProtocol
from .on_receive import OnReceive
from .rfid import RfidCommands
from .serial_protocol import SerialProtocol
from .tcp_protocol import TCPProtocol
from .write_commands import WriteCommands

from smartx_rfid.utils.event import on_event

ant_default_config = {
    "1": {"active": True, "power": 22, "rssi": -120},
    "2": {"active": False, "power": 22, "rssi": -120},
    "3": {"active": False, "power": 22, "rssi": -120},
    "4": {"active": False, "power": 22, "rssi": -120},
}


class X714(SerialProtocol, OnReceive, RfidCommands, BLEProtocol, WriteCommands, TCPProtocol):
    """RFID reader that supports SERIAL, TCP and BLE connections."""

    def __init__(
        self,
        name: str = "X714",
        connection_type: str = "SERIAL",  # SERIAL, BLE or TCP
        # SERIAL
        port: str = "AUTO",  # AUTO or COMx / /dev/ttyX
        baudrate: int = 115200,
        vid: int = 1,
        pid: int = 1,
        # TCP
        ip: str | None = "192.168.1.100",
        tcp_port: int = 23,
        # BLE
        ble_name: str = "SMTX",
        # GENERIC
        buzzer: bool = False,
        session: int = 1,  # 0, 1, 2, 3
        start_reading: bool = False,
        gpi_start: bool = False,
        ignore_read: bool = False,
        always_send: bool = True,
        simple_send: bool = False,
        keyboard: bool = False,
        decode_gtin: bool = False,
        hotspot: bool = True,
        reconnection_time: int = 3,
        prefix: str = "",
        protected_inventory_password: str | None = None,
        # Antenna config
        # If ant_dict is provided use it else use the other vars
        ant_dict: dict | None = None,
        active_ant: list[int] | None = [1],
        read_power: int = 22,
        read_rssi: int = -120,
    ):
        """
        Create X714 RFID reader.

        Args:
            name: Device name
            connection_type: How to connect (SERIAL, TCP, BLE)
            port: Serial port or AUTO to detect
            baudrate: Serial speed
            vid: USB vendor ID for auto-detect
            pid: USB product ID for auto-detect
            ip: IP address for TCP connection
            tcp_port: TCP port number
            ble_name: Bluetooth device name
            buzzer: Make sound when reading tags
            session: EPC session number (0-3)
            start_reading: Start reading tags automatically
            gpi_start: Use GPI input to start reading
            ignore_read: Skip duplicate tags
            always_send: Send all tag events
            simple_send: Use simple tag format
            keyboard: Act like keyboard input
            decode_gtin: Decode GTIN barcodes
            hotspot: Enable hotspot mode
            reconnection_time: Seconds to wait before reconnect
            prefix: Text to add before tag data
            protected_inventory_password: Password for protected reading
            ant_dict: Custom antenna settings
            active_ant: Which antennas to use
            read_power: TX power in dBm
            read_rssi: RSSI threshold in dBm
        """
        # Name
        self.name = name
        self.device_type = "rfid"

        # CONNECTION TYPE
        if connection_type in ["SERIAL", "BLE", "TCP"]:
            self.connection_type = connection_type
        else:
            self.connection_type = "SERIAL"
            logging.warning(f"[{self.name}] Invalid connection_type '{connection_type}' set to 'SERIAL'")

        # SERIAL CONFIG
        self.port = port
        self.baudrate = baudrate
        self.vid = vid
        self.pid = pid
        self.is_auto = self.port == "AUTO"

        # TCP CONFIG
        self.ip = ip
        self.tcp_port = tcp_port

        # BLE CONFIG
        self.ble_name = ble_name
        self.init_ble_vars()

        # GENERIC CONFIG
        self.buzzer = buzzer
        if session not in [0, 1, 2, 3]:
            session = 1
            logging.warning(f"[{self.name}] Invalid session '{session}' set to '1'")
        self.session = session
        self.start_reading = start_reading
        self.gpi_start = gpi_start
        self.ignore_read = ignore_read
        self.always_send = always_send
        self.simple_send = simple_send
        self.keyboard = keyboard
        self.decode_gtin = decode_gtin
        self.hotspot = hotspot
        self.reconnection_time = reconnection_time
        self.prefix = prefix
        self.protected_inventory_password = protected_inventory_password

        # ANTENNA CONFIG
        if ant_dict is not None:
            self.ant_dict = ant_dict
        else:
            self.ant_dict = ant_default_config
            for ant in self.ant_dict.keys():
                ant_num = int(ant)
                if active_ant and ant_num in active_ant:
                    self.ant_dict[ant]["active"] = True
                else:
                    self.ant_dict[ant]["active"] = False
                self.ant_dict[ant]["power"] = read_power
                self.ant_dict[ant]["rssi"] = read_rssi

        self.transport = None
        self.on_con_lost = None
        self.rx_buffer = bytearray()
        self.last_byte_time = None

        self.is_connected = False
        self.is_reading = False

        self.on_event: Callable = on_event

    def write(self, to_send, verbose=True):
        """Send data to reader using current connection type.

        Args:
            to_send: Data to send
            verbose: Show sent data in logs
        """
        if self.connection_type == "SERIAL":
            self.write_serial(to_send, verbose)
        elif self.connection_type == "BLE":
            asyncio.create_task(self.write_ble(to_send.encode(), verbose))
        else:
            asyncio.create_task(self.write_tcp(to_send, verbose))

    async def connect(self):
        """Connect to reader using configured connection type."""
        if self.connection_type == "SERIAL":
            await self.connect_serial()
        elif self.connection_type == "BLE":
            await self.connect_ble()
        else:
            await self.connect_tcp(self.ip, self.tcp_port)

    def on_connected(self):
        """Called when connection is established. Sets up reader."""
        self.config_reader()
        self.on_event(self.name, "connected", True)
