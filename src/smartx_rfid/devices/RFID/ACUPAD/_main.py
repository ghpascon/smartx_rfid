import asyncio
import logging
import time
from smartx_rfid.schemas import TagSchema
import serial.tools.list_ports
import serial_asyncio
from typing import Callable
from smartx_rfid.utils.event import on_event


from smartx_rfid.devices._base import DeviceBase


class ACUPAD(DeviceBase, asyncio.Protocol):
    """
    Asynchronous Serial Communication Protocol Handler

    This class implements an asyncio-based serial communication protocol
    that supports automatic port detection, connection management, and
    data handling with timeout mechanisms.

    Features:
    - Automatic port detection by VID/PID
    - Automatic reconnection on connection loss
    - Message buffering with timeout handling
    - CRC16 checksum calculation
    - Event-driven architecture
    """

    def __init__(
        self,
        name: str = "ACUPAD",
        port: str = "AUTO",
        baudrate: int = 115200,
        vid: int = 1003,
        pid: int = 8192,
        reconnection_time: int = 3,
        start_reading: bool = True,
        session: int = 1,
        read_power: int = 22,
        read_rssi: int = 0,
        active_ant: list[int] = [1],
        beep: bool = False,
        **kwargs,
    ):
        """
        Initialize the SERIAL protocol handler.

        Args:
                name: Device name identifier
                port: Serial port ('AUTO' for automatic detection)
                baudrate: Communication baudrate
                vid: USB Vendor ID for auto-detection
                pid: USB Product ID for auto-detection
                reconnection_time: Delay between reconnection attempts
        """
        DeviceBase.__init__(self)
        self.name = name
        self.device_type = "rfid"

        self.port = port
        self.baudrate = baudrate
        self.vid = vid
        self.pid = pid
        self.reconnection_time = reconnection_time

        self.transport = None
        self.on_con_lost = None
        self.rx_buffer = bytearray()
        self.last_byte_time = None
        self.is_auto = self.port == "AUTO"

        self.is_connected = False
        self.is_reading = False

        if not isinstance(start_reading, bool):
            start_reading = True
        self.start_reading = start_reading

        if session not in [0, 1, 2, 3]:
            session = 1
        self.session = session

        if not isinstance(read_power, int):
            read_power = 22
        if read_power < 10 or read_power > 30:
            read_power = 22
        self.read_power = read_power

        if not isinstance(read_rssi, int):
            read_rssi = 0
        if read_rssi < 20 or read_rssi > 99:
            read_rssi = 0

        self.read_rssi = read_rssi

        if not isinstance(active_ant, list):
            active_ant = [1]
        self.active_ant = active_ant

        if not isinstance(beep, bool):
            beep = False
        self.beep = beep
        self.on_event: Callable = on_event

    def connection_made(self, transport):
        """
        Callback invoked when a connection is established.

        Args:
                transport: The transport object for communication
        """
        self.transport = transport
        self.is_connected = True
        self.on_event(self.name, "connection", True)
        self.config_reader()

    def data_received(self, data):
        """
        Callback invoked when data is received from the serial port.

        Handles incoming data with automatic message parsing and timeout management.
        Messages are delimited by '\n' or '\r' characters.

        Args:
                data: Raw bytes received from the serial port
        """
        now = time.time()
        self.rx_buffer += data
        self.last_byte_time = now

        # Cancela tarefa anterior de timeout
        if hasattr(self, "_timeout_task") and self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        # Cria nova tarefa de timeout
        async def timeout_clear():
            await asyncio.sleep(0.3)  # 300 ms
            if self.last_byte_time and (time.time() - self.last_byte_time) >= 0.3:
                if self.rx_buffer:
                    self.rx_buffer.clear()
                    logging.warning("⚠️ Buffer cleared due to 300ms timeout without receiving data.")

        self._timeout_task = self.create_task(timeout_clear())

        # Processa mensagens completas
        while b"\n" in self.rx_buffer or b"\r" in self.rx_buffer:
            # Encontra posição do primeiro delimitador
            positions = [p for p in [self.rx_buffer.find(b"\n"), self.rx_buffer.find(b"\r")] if p != -1]
            pos = min(positions)

            # Extrai mensagem em bytes e converte para string
            message_bytes = self.rx_buffer[:pos]
            message = message_bytes.decode(errors="ignore").strip("\r\n")

            # Remove mensagem do buffer
            self.rx_buffer = self.rx_buffer[pos + 1 :]

            if message:
                message = message.replace(">", "")
                self.on_receive(message)

    def connection_lost(self, exc):
        """
        Callback invoked when the connection is lost.

        Args:
                exc: Exception that caused the disconnection (if any)
        """
        logging.warning("⚠️ Serial connection lost.")
        self.transport = None
        self.is_connected = False
        self.step = 0

        if self.on_con_lost:
            self.on_con_lost.set()
        self.on_event(self.name, "connection", False)

    def write(self, to_send, verbose=False):
        """
        Send data through serial port.

        Args:
            to_send: Data to send (string or bytes)
            verbose: Show sent data in logs
        """
        if self.transport:
            if isinstance(to_send, str):
                to_send += "\r"
                if verbose:
                    logging.info(f"📤 Sending: {to_send}")

                to_send = to_send.encode()
                self.transport.write(to_send)
                return

            # If it's bytes, calculate CRC and replace last two bytes
            if isinstance(to_send, bytes) and len(to_send) >= 2:
                crc = self.crc16(to_send)
                to_send = to_send[:-2] + bytes([crc & 0xFF, crc >> 8])

                if verbose:
                    hex_list = [f"0x{b:02X}" for b in to_send]
                    logging.info(f"📤 Sending: {hex_list}")

            self.transport.write(to_send)
        else:
            logging.warning("❌ Send attempt failed: connection not established.")

    async def connect(self):
        """Connect to serial port and keep connection alive."""
        """
        Establish and maintain serial connection with automatic reconnection.

        This method runs continuously, attempting to connect to the specified
        serial port or auto-detecting it by VID/PID. When connection is lost,
        it automatically attempts to reconnect.
        """
        loop = asyncio.get_running_loop()

        while self._running:
            self.on_con_lost = asyncio.Event()

            # If AUTO mode, try to detect port by VID/PID
            if self.is_auto:
                logging.info("🔍 Auto-detecting port")
                ports = serial.tools.list_ports.comports()
                found_port = None
                for p in ports:
                    # p.vid and p.pid are integers (e.g. 0x0001 == 1 decimal)
                    if p.vid == self.vid and p.pid == self.pid:
                        found_port = p.device
                        logging.info(f"✅ Detected port: {found_port}")
                        break

                if found_port is None:
                    logging.warning(f"⚠️ No port with VID={self.vid} and PID={self.pid} found.")
                    logging.info(f"⏳ Retrying in {self.reconnection_time} seconds...")
                    await asyncio.sleep(self.reconnection_time)
                    continue  # try to detect again in next loop
                else:
                    self.port = found_port

            try:
                logging.info(f"🔌 Trying to connect to {self.port} at {self.baudrate} bps...")
                await serial_asyncio.create_serial_connection(loop, lambda: self, self.port, baudrate=self.baudrate)
                logging.info("🟢 Successfully connected.")
                await self.on_con_lost.wait()
                logging.info("🔄 Connection lost. Attempting to reconnect...")
            except Exception as e:
                logging.warning(f"❌ Connection error: {e}")

            # If in AUTO mode, reset port to "AUTO" to force detection next loop
            if self.is_auto:
                self.port = "AUTO"

            logging.info("⏳ Waiting 3 seconds before retrying...")
            await asyncio.sleep(3)

    async def close(self):
        """Shut down background tasks and close transport for this device."""
        # stop connect loop
        self._running = False

        # signal on_con_lost to break any waits
        try:
            if self.on_con_lost and not self.on_con_lost.is_set():
                self.on_con_lost.set()
        except Exception:
            pass

        # close transport if present
        try:
            if self.transport:
                try:
                    self.transport.close()
                except Exception:
                    pass
                self.transport = None
        except Exception:
            pass

        await self.shutdown()

    def crc16(self, data: bytes, poly=0x8408):
        """
        Calculate CRC16 checksum for data validation.

        Args:
            data: Input bytes to calculate checksum
            poly: CRC polynomial value

        Returns:
            int: 16-bit checksum value
        """
        """
        Calculate CRC-16/CCITT-FALSE checksum.

        Args:
                data: Input bytes (last 2 bytes are excluded from calculation)
                poly: CRC polynomial (default: 0x8408 for CCITT-FALSE)

        Returns:
                int: 16-bit CRC checksum
        """
        crc = 0xFFFF
        for byte in data[:-2]:  # exclude last two bytes (CRC placeholder)
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
        return crc & 0xFFFF

    async def start_inventory(self):
        self.write("readtag on", verbose=True)
        self.is_reading = True

    async def stop_inventory(self):
        self.write("readtag off", verbose=True)
        self.is_reading = False

    def config_reader(self):
        self.write("readmode serial")
        self.write("tagop tid:0:6")
        self.write(f"gen2session s{self.session}")
        self.write("gen2q 4")
        self.write("gen2target ab")
        self.write("epcdecode none")
        self.write("separator ;")
        self.write(f"rssifilter {self.read_rssi}")
        self.write("reportrssi on")
        self.write("tagtimeout 0")
        self.write("reportantenna on")
        self.write(
            f"antennaport {''.join(str(ant) for ant in self.active_ant) if len(self.active_ant) > 0 else 'none'}"
        )
        self.write(f"enablebeep {'on' if self.beep else 'off'}")
        self.write("reportreadcount off")
        self.write("selectfilter none")
        self.write(f"readpowerport1 {self.read_power}")
        self.write(f"readpowerport2 {self.read_power}")
        self.write("initreadtag off")

        if self.start_reading:
            self.create_task(self.start_inventory())
        else:
            self.create_task(self.stop_inventory())

    def on_receive(self, message: str):
        if message.startswith("ok"):
            return
        if len(message) == 55:
            try:
                epc, tid, rssi, ant = message.split(";")
                tag = TagSchema(
                    epc=epc,
                    tid=tid,
                    ant=int(ant),
                    rssi=int(rssi) * (-1),
                ).model_dump()

                self.on_event(self.name, "tag", tag)
                return
            except Exception as e:
                logging.error(f"Error parsing tag data: {e}")

        self.on_event(self.name, "receive", message)
