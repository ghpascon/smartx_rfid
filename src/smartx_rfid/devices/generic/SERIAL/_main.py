import asyncio
import logging
import time

import serial.tools.list_ports
import serial_asyncio
from typing import Callable
from smartx_rfid.utils.event import on_event


class SERIAL(asyncio.Protocol):
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
        name: str = "GENERIC_SERIAL",
        port: str = "AUTO",
        baudrate: int = 115200,
        vid: int = 1,
        pid: int = 1,
        reconnection_time: int = 3,
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
        self.name = name
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

        self._timeout_task = asyncio.create_task(timeout_clear())

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
                self.on_event(self.name, "receive", message)

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

    def write(self, to_send, verbose=True):
        """
        Send data through the serial connection.

        Automatically adds newline to strings and calculates CRC16 for bytes.

        Args:
                to_send: Data to send (str or bytes)
                verbose: Enable logging of sent data
        """
        if self.transport:
            if isinstance(to_send, str):
                to_send += "\n"
                to_send = to_send.encode()

            # If it's bytes, calculate CRC and replace last two bytes
            if isinstance(to_send, bytes) and len(to_send) >= 2:
                crc = self.crc16(to_send)
                to_send = to_send[:-2] + bytes([crc & 0xFF, crc >> 8])

            if verbose:
                if isinstance(to_send, bytes):
                    hex_list = [f"0x{b:02X}" for b in to_send]
                    logging.info(f"📤 Sending: {hex_list}")
                else:
                    logging.info(f"📤 Sending: {to_send}")

            self.transport.write(to_send)
        else:
            logging.warning("❌ Send attempt failed: connection not established.")

    async def connect(self):
        """
        Establish and maintain serial connection with automatic reconnection.

        This method runs continuously, attempting to connect to the specified
        serial port or auto-detecting it by VID/PID. When connection is lost,
        it automatically attempts to reconnect.
        """
        loop = asyncio.get_running_loop()

        while True:
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

    def crc16(self, data: bytes, poly=0x8408):
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
