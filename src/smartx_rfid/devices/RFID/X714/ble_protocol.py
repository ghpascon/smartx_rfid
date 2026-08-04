import asyncio
import logging
import sys
import threading
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

if sys.platform == "win32":
    try:
        from bleak.backends.winrt.util import allow_sta

        allow_sta()
    except ImportError:
        pass

# ---------------- Settings ----------------
SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
CHARACTERISTIC_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write (ESP32 receives)
CHARACTERISTIC_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify (ESP32 sends)


class BLEProtocol:
    def init_ble_vars(self):
        self.client_ble: Optional[BleakClient] = None
        self._ble_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ble_thread: Optional[threading.Thread] = None
        self.ble_stop = False
        self.notify_enabled = False

    # ---------------- Utilities ----------------
    async def write_ble(self, data: bytes, verbose: bool = False) -> bool:
        """Send data via BLE with connection check."""
        if not self.client_ble or not self.client_ble.is_connected:
            logging.warning(f"{self.name} - ⚠️ BLE client not connected")
            return False
        try:
            await self.client_ble.write_gatt_char(CHARACTERISTIC_RX, data)
            if verbose:
                logging.info(f"{self.name} - [BLE TX] {data}")
            return True
        except Exception as e:
            logging.warning(f"{self.name} - [BLE Write Error] {e}")
            return False

    async def scan_for_device(self) -> Optional[str]:
        """Scan for devices whose name starts with the defined prefix."""
        while not self.ble_stop:
            logging.info(f"{self.name} - 🔍 Scanning BLE devices...")
            try:
                devices = await BleakScanner.discover(timeout=5.0)
                for d in devices:
                    if d.name and d.name.startswith(self.ble_name):
                        logging.info(f"{self.name} - ✅ Device found: {d.address} ({d.name})")
                        return d.address
                logging.warning(f"{self.name} - ❌ Device not found, retrying...")
            except Exception as e:
                logging.warning(f"{self.name} - [Scan Error] {e}")
            await asyncio.sleep(self.reconnection_time)
        return None

    def _set_disconnected(self):
        """Mark device as disconnected and fire event."""
        if self.is_connected:
            self.is_connected = False
            self.is_reading = False
            self.serial_number = None

    # ---------------- Main Connection ----------------
    async def connect_and_run(self):
        """Main BLE connection and operation loop."""
        while not self.ble_stop:
            try:
                self._set_disconnected()

                # Escolhe o endereço conforme o modo
                if self.is_auto:
                    address = await self.scan_for_device()
                    if not address:
                        continue
                else:
                    address = self.connection  # Usa o MAC address fixo
                    logging.info(f"{self.name} - 🔗 Using fixed BLE address: {address}")

                logging.info(f"{self.name} - Attempting to connect to {address}...")

                # disconnected_callback permite detectar queda imediata do hardware
                disconnected_event = asyncio.Event()

                def handle_disconnect(_client: BleakClient):
                    disconnected_event.set()

                # async with gerencia connect/disconnect automaticamente — não chame
                # client.connect() explicitamente antes, pois causaria double-connect.
                try:
                    async with BleakClient(
                        address,
                        disconnected_callback=handle_disconnect,
                        timeout=10.0,
                    ) as client:
                        logging.info(f"{self.name} - 🔗 Connected to device")
                        self.client_ble = client

                        def handle_notification(sender, data: bytearray):
                            self.on_receive(data.decode(errors="ignore"))

                        # Log all available services and characteristics
                        logging.info(f"{self.name} - Available services and characteristics:")
                        for service in client.services:
                            logging.info(f"  Service: {service.uuid}")
                            for char in service.characteristics:
                                logging.info(f"    Characteristic: {char.uuid} | properties: {char.properties}")

                        # Tenta registrar na característica TX conhecida
                        self.notify_enabled = False
                        try:
                            logging.info(f"{self.name} - Attempting to start notify on {CHARACTERISTIC_TX}...")
                            await client.start_notify(CHARACTERISTIC_TX, handle_notification)
                            logging.info(f"{self.name} - ✅ Notify started on {CHARACTERISTIC_TX}")
                            self.notify_enabled = True
                        except Exception as e:
                            logging.warning(f"{self.name} - [Notify TX Error] {e} — trying fallback...")
                            for service in client.services:
                                for char in service.characteristics:
                                    if "notify" in char.properties:
                                        try:
                                            await client.start_notify(char.uuid, handle_notification)
                                            self.notify_enabled = True
                                            logging.info(f"{self.name} - ✅ Fallback notify on {char.uuid}")
                                        except Exception as e2:
                                            logging.warning(f"{self.name} - [Notify Fallback Error] {char.uuid}: {e2}")
                                        if self.notify_enabled:
                                            break
                                if self.notify_enabled:
                                    break

                        logging.info(f"{self.name} - Notify enabled: {self.notify_enabled}")
                        if not self.notify_enabled:
                            logging.warning(f"{self.name} - ⚠️ No notify characteristic found, retrying...")
                            await asyncio.sleep(self.reconnection_time)
                            continue

                        self.is_connected = True
                        if hasattr(self, "on_connected"):
                            self.on_connected()
                        logging.info(f"{self.name} - ✅ BLE connection successfully established.")

                        # Loop de manutenção
                        loop = asyncio.get_running_loop()
                        last_ping = loop.time()
                        while client.is_connected and not self.ble_stop and not disconnected_event.is_set():
                            now = loop.time()
                            if now - last_ping >= 5:
                                # Envia um ping e valida retorno; se falhar, assume desconexão
                                try:
                                    success = await self.write_ble(b"#ping")
                                except Exception as e:
                                    logging.warning(f"{self.name} - [Ping Error] {e}")
                                    success = False
                                last_ping = now
                                if not success:
                                    logging.warning(
                                        f"{self.name} - ⚠️ Ping falhou — assumindo desconexão e forçando reconnect"
                                    )
                                    try:
                                        # Tenta parar notify para acelerar desconexão
                                        if self.notify_enabled:
                                            try:
                                                await client.stop_notify(CHARACTERISTIC_TX)
                                            except Exception:
                                                # tenta fallback para quaisquer características notify
                                                for service in client.services:
                                                    for char in service.characteristics:
                                                        if "notify" in char.properties:
                                                            try:
                                                                await client.stop_notify(char.uuid)
                                                                break
                                                            except Exception:
                                                                pass
                                    except Exception:
                                        pass
                                    break
                            await asyncio.sleep(0.5)

                        logging.info(f"{self.name} - 🔌 Disconnected from device.")

                except asyncio.TimeoutError:
                    logging.warning(f"{self.name} - ⏰ Connection attempt timed out")
                    await asyncio.sleep(self.reconnection_time)
                    continue

            except BleakError as e:
                logging.warning(f"{self.name} - [BLE Error] {e}")
                await asyncio.sleep(self.reconnection_time)
            except Exception as e:
                logging.warning(f"{self.name} - [Unexpected BLE Error] {e}")
                await asyncio.sleep(self.reconnection_time)
            finally:
                self.client_ble = None
                self._set_disconnected()

    # ---------------- Thread Wrapper ----------------
    async def connect_ble(self):
        """Start BLE connection loop in a background thread.

        Declared async so it can be awaited in async contexts (e.g. _main.py),
        even though the actual loop runs in a separate OS thread.

        Important: keep this coroutine alive while BLE thread is running.
        Some managers await `connect()` and interpret a quick return as finish,
        triggering cleanup immediately.
        """

        if self._ble_thread and self._ble_thread.is_alive():
            logging.info(f"{self.name} - BLE thread already running")
        else:
            self.ble_stop = False

            def run_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._ble_loop = loop
                try:
                    loop.run_until_complete(self.connect_and_run())
                finally:
                    loop.close()
                    self._ble_loop = None

            self._ble_thread = threading.Thread(target=run_loop, daemon=True, name=f"ble-{self.name}")
            self._ble_thread.start()

        while not self.ble_stop:
            if self._ble_thread and not self._ble_thread.is_alive():
                logging.warning(f"{self.name} - BLE thread stopped unexpectedly")
                break
            await asyncio.sleep(0.2)

    async def close_ble(self):
        """Stop BLE loop and force disconnect."""
        self.ble_stop = True
        if self.client_ble and self.client_ble.is_connected:
            try:
                await self.client_ble.disconnect()
            except Exception:
                pass

    def stop(self):
        """Request BLE loop stop."""
        logging.info(f"{self.name} - 🛑 Stopping BLE loop...")
        self.ble_stop = True
