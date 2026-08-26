import asyncio
import logging
import socket


class TCPHelpers:
    async def monitor_connection(self):
        while self.is_connected:
            await asyncio.sleep(self.reconnection_time)
            if (self.writer and self.writer.is_closing()) or (self.reader and self.reader.at_eof()):
                self.is_connected = False
                self.is_reading = False
                logging.info(f"{self.name} - [DISCONNECTED] Socket closed.")
                break

            await self.write_tcp("ping", verbose=False)

    async def receive_data_tcp(self):
        buffer = ""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(self.reader.read(1024), timeout=0.1)
                except asyncio.TimeoutError:
                    # Timeout: process what's in the buffer as a command
                    if buffer:
                        self.on_receive(buffer.strip())
                        buffer = ""
                    continue

                if not data:
                    raise ConnectionError("Connection lost")

                buffer += data.decode(errors="ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self.on_receive(line.strip())

        except Exception as e:
            if self.is_connected:
                self.is_connected = False
                self.is_reading = False
                logging.warning(f"[RECEIVE ERROR] {e}")


class TCPProtocol(TCPHelpers):
    async def connect_tcp(self, ip, port):
        # respeita self._running para permitir parada limpa
        while getattr(self, "_running", True):
            await asyncio.sleep(self.reconnection_time)
            try:
                logging.info(f"Connecting: {self.name} - {ip}:{port}")

                # Verifica IP antes (evita travar no DNS)
                try:
                    resolved_ip = socket.gethostbyname(ip)
                except OSError:
                    raise ValueError(f"Invalid IP address: {ip}")

                # Tenta abrir conexão com timeout real
                connect_task = asyncio.open_connection(resolved_ip, port)
                self.reader, self.writer = await asyncio.wait_for(connect_task, timeout=3)

                self.is_connected = True
                self.on_connected()
                logging.info(f"✅ [CONNECTED] {self.name} - {ip}:{port}")

                # try to enable TCP keepalive on the underlying socket to help
                # detect dead peers (e.g., cable unplug). Parameters are platform
                # specific; set them if available but ignore errors.
                try:
                    sock = None
                    if self.writer:
                        sock = self.writer.get_extra_info("socket")
                    if sock is not None:
                        try:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        except Exception:
                            pass
                        # Linux-specific tuning (may not exist on all platforms)
                        try:
                            if hasattr(socket, "TCP_KEEPIDLE"):
                                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                            if hasattr(socket, "TCP_KEEPINTVL"):
                                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)
                            if hasattr(socket, "TCP_KEEPCNT"):
                                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                        except Exception:
                            pass
                except Exception:
                    pass
                # Cria tasks de leitura e monitoramento (usando tracking se disponível)
                tasks = [
                    self.create_task(self.receive_data_tcp())
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.receive_data_tcp()),
                    self.create_task(self.monitor_connection())
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.monitor_connection()),
                    self.create_task(self.periodic_ping(10))
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.periodic_ping(10)),
                ]

                # Espera até que uma delas finalize
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                # Cancela o resto
                for t in pending:
                    t.cancel()

                self.is_connected = False
                self.is_reading = False
                self.serial_number = None

                logging.info(f"🔌 [DISCONNECTED] {self.name} - Reconnecting...")

            except asyncio.TimeoutError:
                logging.warning(f"⏱️ [TIMEOUT] {self.name} - No response from {ip}:{port}")
                continue
            except ValueError as e:
                logging.warning(f"❌ [INVALID IP] {self.name}: {e}")
                continue
            except OSError as e:
                logging.warning(f"💥 [NETWORK ERROR] {self.name}: {e}")
                continue
            except Exception as e:
                logging.warning(f"❌ [UNEXPECTED ERROR] {self.name}: {e}")
                continue

            # Garante desconexão limpa
            if self.writer:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass
                self.serial_number = None
                self.writer = None
                self.reader = None
                self.is_connected = False
                self.is_reading = False

            logging.info(f"🔁 Retrying {self.name} in {self.reconnection_time}s...")

    async def write_tcp(self, data: str, verbose: bool = True):
        if self.is_connected and self.writer:
            try:
                data = data + "\n"
                self.writer.write(data.encode())
                # Wait for drain but guard with a timeout so a stalled TCP stack
                # (e.g., due to unplugged cable) doesn't hang indefinitely.
                try:
                    # choose a conservative timeout (at least 1s)
                    timeout = max(1.0, getattr(self, "reconnection_time", 1) * 2)
                    await asyncio.wait_for(self.writer.drain(), timeout=timeout)
                except asyncio.TimeoutError:
                    logging.warning(f"{self.name} - [SEND TIMEOUT] drain() timed out")
                    raise
                if verbose:
                    logging.info(f"{self.name} - [SENT] {data.strip()}")
            except Exception as e:
                logging.warning(f"{self.name} - [SEND ERROR] {e}")
                if self.is_connected:
                    self.is_connected = False
                    self.is_reading = False
                    self.serial_number = None

    async def periodic_ping(self, interval: int):
        while self.is_connected:
            await asyncio.sleep(interval)
            await self.write_tcp("ping", verbose=False)
