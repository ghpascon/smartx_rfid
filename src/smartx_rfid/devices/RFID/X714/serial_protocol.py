import asyncio
import logging

import serial.tools.list_ports
import serial_asyncio


class SerialProtocol(asyncio.Protocol):
	def connection_made(self, transport):
		self.transport = transport
		self.is_connected = True
		logging.info(f'{self.name} - ✅ Serial connection successfully established.')
		self.on_connected()

	def data_received(self, data):
		self.rx_buffer += data

		while b'\n' in self.rx_buffer:
			idx = self.rx_buffer.index(b'\n')
			packet = self.rx_buffer[:idx]
			self.rx_buffer = self.rx_buffer[idx + 1 :]
			self.on_receive(packet)

	def connection_lost(self, exc):
		logging.warning(f'{self.name} - ⚠️ Serial connection lost.')
		self.transport = None
		self.is_connected = False
		self.on_event(self.name, 'connection', False)

		if self.on_con_lost:
			self.on_con_lost.set()

	def write_serial(self, to_send, verbose=True):
		if self.transport:
			if verbose:
				logging.info(f'{self.name} - 📤 Sending: {to_send}')
			if isinstance(to_send, str):
				to_send += '\n'
				to_send = to_send.encode()  # convert string to bytes
			self.transport.write(to_send)
		else:
			logging.warning(f'{self.name} - ❌ Send attempt failed: connection not established.')

	async def connect_serial(self):
		"""Serial connection/reconnection loop"""
		loop = asyncio.get_running_loop()

		asyncio.create_task(self.auto_clear())

		while True:
			self.on_con_lost = asyncio.Event()

			# If AUTO mode, try to detect port by VID/PID
			if self.is_auto:
				logging.info(f'{self.name} - 🔍 Auto-detecting port by VID={self.vid:04x} and PID={self.pid:04x}...')
				ports = serial.tools.list_ports.comports()
				found_port = None
				for p in ports:
					# p.vid and p.pid are integers (e.g. 0x0001 == 1 decimal)
					if p.vid == self.vid and p.pid == self.pid:
						found_port = p.device
						logging.info(f'{self.name} - ✅ Detected port: {found_port}')
						break

				if found_port is None:
					logging.info(f'{self.name} - ⚠️ No port with VID={self.vid} and PID={self.pid} found.')
					logging.info(f'{self.name} - ⏳ Retrying in {self.reconnection_time} seconds...')
					await asyncio.sleep(self.reconnection_time)
					continue  # try to detect again in next loop
				else:
					self.connection = found_port

			try:
				logging.info(f'{self.name} - 🔌 Trying to connect to {self.connection} at {self.baudrate} bps...')
				await serial_asyncio.create_serial_connection(
					loop, lambda: self, self.connection, baudrate=self.baudrate
				)
				logging.info(f'{self.name} - 🟢 Successfully connected.')
				await self.on_con_lost.wait()
				logging.info(f'{self.name} - 🔄 Connection lost. Attempting to reconnect...')
			except Exception as e:
				logging.warning(f'{self.name} - ❌ Connection error: {e}')

			# If in AUTO mode, reset port to "AUTO" to force detection next loop
			if self.is_auto:
				self.connection = 'AUTO'

			logging.info(f'{self.name} - ⏳ Waiting {self.reconnection_time} seconds before retrying...')
			await asyncio.sleep(self.reconnection_time)
