import asyncio
import logging
import threading
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.winrt.util import allow_sta
from bleak.exc import BleakError

allow_sta()  # Required on Windows

# ---------------- Settings ----------------
SERVICE_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
CHARACTERISTIC_RX = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'  # Write (ESP32 receives)
CHARACTERISTIC_TX = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'  # Notify (ESP32 sends)


class BLEProtocol:
	def init_ble_vars(self):
		self.client_ble: Optional[BleakClient] = None
		self.client_ble_lock = asyncio.Lock()
		self.connected_ble_event = asyncio.Event()
		self.ble_stop = False
		self.notify_enabled = False

	# ---------------- Utilities ----------------
	async def write_ble(self, data: bytes, verbose: bool = False) -> bool:
		"""Send data via BLE with connection check and lock."""
		if not self.client_ble or not self.client_ble.is_connected:
			logging.warning(f'{self.name} - ⚠️ BLE client not connected')
			return False
		async with self.client_ble_lock:
			try:
				await self.client_ble.write_gatt_char(CHARACTERISTIC_RX, data)
				if verbose:
					logging.info(f'{self.name} - [BLE TX] {data}')
				return True
			except Exception as e:
				logging.warning(f'{self.name} - [BLE Write Error] {e}')
				return False

	async def scan_for_device(self) -> Optional[str]:
		"""Scan for devices whose name starts with the defined prefix."""
		while not self.ble_stop:
			logging.info(f'{self.name} - 🔍 Scanning BLE devices...')
			try:
				devices = await BleakScanner.discover(timeout=5.0)
				for d in devices:
					if d.name and d.name.startswith(self.ble_name):
						logging.info(f'{self.name} - ✅ Device found: {d.address} ({d.name})')
						return d.address
				logging.warning(f'{self.name} - ❌ Device not found, retrying in 3s...')
			except Exception as e:
				logging.warning(f'{self.name} - [Scan Error] {e}')
			await asyncio.sleep(self.reconnection_time)
		return None

	# ---------------- Main Connection ----------------
	async def connect_and_run(self):
		"""Main BLE connection and operation loop."""
		while not self.ble_stop:
			try:
				# Se já estava conectado antes, emite o evento de desconexão
				if self.is_connected:
					self.is_connected = False
					self.on_event(self.name, 'connection', False)

				# Escolhe o endereço conforme o modo
				if self.is_auto:
					address = await self.scan_for_device()
					if not address:
						continue
				else:
					address = self.connection  # Usa o MAC address fixo
					logging.info(f'{self.name} - 🔗 Using fixed BLE address: {address}')

				logging.info(f'{self.name} - Attempting to connect to {address}...')
				client = BleakClient(address)

				try:
					await asyncio.wait_for(client.connect(), timeout=5.0)
				except asyncio.TimeoutError:
					logging.warning(f'{self.name} - ⏰ Connection attempt timed out')
					await asyncio.sleep(self.reconnection_time)
					continue

				if not client.is_connected:
					logging.warning(f'{self.name} - ❌ Failed to connect.')
					await asyncio.sleep(self.reconnection_time)
					continue

				async with client:
					logging.info(f'{self.name} - 🔗 Connected to device')
					self.client_ble = client
					self.connected_ble_event.set()

					# Notification callback
					def handle_notification(sender, data: bytearray):
						decoded = data.decode(errors='ignore')
						self.on_receive(decoded)

					# Habilita notificações automaticamente
					self.notify_enabled = False
					for service in client.services:
						for char in service.characteristics:
							if 'notify' in char.properties:
								try:
									await client.start_notify(char.uuid, handle_notification)
									self.is_connected = True
									self.on_event(self.name, 'connection', True)
									logging.info(f'{self.name} - ✅ BLE connection successfully established.')
									self.config_reader()
									self.notify_enabled = True
								except Exception as e:
									logging.warning(f'{self.name} - [Notify Error] {char.uuid}: {e}')
					if not self.notify_enabled:
						logging.warning(f'{self.name} - ⚠️ No characteristics with notify property found!')
					# Loop principal de manutenção da conexão
					last_ping = 0
					while client.is_connected and not self.ble_stop:
						now = asyncio.get_event_loop().time()
						if now - last_ping >= 5:
							await self.write_ble(b'#ping')
							last_ping = now
						await asyncio.sleep(1)

					logging.info(f'{self.name} - 🔌 Disconnected from device.')

			except BleakError as e:
				logging.warning(f'{self.name} - [BLE Error] {e}')
				await asyncio.sleep(self.reconnection_time)
			except Exception as e:
				logging.warning(f'{self.name} - [Unexpected BLE Error] {e}')
				await asyncio.sleep(self.reconnection_time)
			finally:
				self.connected_ble_event.clear()
				self.client_ble = None

	# ---------------- Thread Wrapper ----------------
	def connect_ble(self):
		"""Run BLE loop in a separate thread (ideal for FastAPI)."""

		def run_loop():
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			loop.run_until_complete(self.connect_and_run())

		threading.Thread(target=run_loop, daemon=True).start()

	def stop(self):
		"""Request BLE loop stop."""
		logging.info(f'{self.name} - 🛑 Stopping BLE loop...')
		self.ble_stop = True
