import asyncio
import logging
import socket


class TCPHelpers:
    def _is_tcp_transport_closed(self) -> bool:
        """Best-effort check for closed TCP transport state."""
        writer = getattr(self, "writer", None)
        if writer:
            try:
                # High-level check first
                if writer.is_closing():
                    return True
            except Exception:
                return True

            # Try to inspect the underlying socket for platform-level errors.
            try:
                sock = writer.get_extra_info("socket")
                if sock is None:
                    # If there's no socket attached, consider the transport closed.
                    return True
                try:
                    fileno = sock.fileno()
                    if fileno < 0:
                        return True
                except Exception:
                    pass
                try:
                    err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if err != 0:
                        return True
                except Exception:
                    # If getsockopt fails, ignore and continue with other checks.
                    pass
            except Exception:
                return True

        reader = getattr(self, "reader", None)
        if reader:
            try:
                if reader.at_eof():
                    return True
            except Exception:
                return True

        return False

    async def _mark_tcp_disconnected(self, reason: str | None = None):
        """Atomically mark TCP link as disconnected and cleanup stream state."""
        writer = getattr(self, "writer", None)

        self.is_connected = False
        self.is_reading = False
        self.serial_number = None
        self.writer = None
        self.reader = None

        if writer:
            try:
                writer.close()
            except Exception:
                pass

            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await wait_closed()
                except Exception:
                    pass

        if reason:
            logging.info(reason)

    async def monitor_connection(self):
        while self.is_connected:
            await asyncio.sleep(self.reconnection_time)
            if self._is_tcp_transport_closed():
                await self._mark_tcp_disconnected(f"{self.name} - [DISCONNECTED] Socket closed.")
                break

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
                logging.warning(f"[RECEIVE ERROR] {e}")
                await self._mark_tcp_disconnected(f"{self.name} - [DISCONNECTED] Receive loop stopped.")


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
                            # Bound retransmission time for unacked data to detect
                            # dead links (e.g. unplugged cable) sooner on Linux.
                            if hasattr(socket, "TCP_USER_TIMEOUT"):
                                user_timeout_ms = max(
                                    5000,
                                    int(getattr(self, "reconnection_time", 3) * 3000),
                                )
                                sock.setsockopt(
                                    socket.IPPROTO_TCP,
                                    socket.TCP_USER_TIMEOUT,
                                    user_timeout_ms,
                                )
                        except Exception:
                            pass
                except Exception:
                    pass
                # Cria tasks de leitura e monitoramento (usando tracking se disponível)
                # Create background tasks: receiver, monitor and periodic pinger.
                tasks = [
                    self.create_task(self.receive_data_tcp())
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.receive_data_tcp()),
                    self.create_task(self.monitor_connection())
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.monitor_connection()),
                    self.create_task(self.periodic_ping(5))
                    if hasattr(self, "create_task")
                    else asyncio.create_task(self.periodic_ping(5)),
                ]

                # Espera até que uma delas finalize
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                # Coleta possíveis exceções da tarefa que finalizou
                for finished in done:
                    try:
                        finished.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as task_error:
                        logging.warning(f"{self.name} - [TASK ERROR] {task_error}")

                # Cancela o resto
                for t in pending:
                    t.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

                await self._mark_tcp_disconnected()

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
            await self._mark_tcp_disconnected()

            logging.info(f"🔁 Retrying {self.name} in {self.reconnection_time}s...")

    async def write_tcp(self, data: str, verbose: bool = True):
        if not (getattr(self, "is_connected", False) and getattr(self, "writer", None)):
            return False

        writer = self.writer
        try:
            data_line = data if data.endswith("\n") else data + "\n"
            writer.write(data_line.encode())

            # Run drain in a separate task so it can be cancelled if it hangs.
            drain_coro = writer.drain()
            drain_task = asyncio.create_task(drain_coro)
            try:
                timeout = max(1.0, getattr(self, "reconnection_time", 1) * 2)
                await asyncio.wait_for(drain_task, timeout=timeout)
            except asyncio.TimeoutError:
                logging.warning(f"{self.name} - [SEND TIMEOUT] drain() timed out")
                # Best-effort cancel and cleanup.
                try:
                    drain_task.cancel()
                    # Use gather with return_exceptions to avoid propagating
                    # CancelledError out of this function in tests and runtime.
                    await asyncio.gather(drain_task, return_exceptions=True)
                except Exception:
                    pass
                raise

            if verbose:
                logging.info(f"{self.name} - [SENT] {data_line.strip()}")
            return True
        except Exception as e:
            logging.warning(f"{self.name} - [SEND ERROR] {e}")
            if getattr(self, "is_connected", False):
                await self._mark_tcp_disconnected(f"{self.name} - [DISCONNECTED] Send failed.")
            return False

    async def periodic_ping(self, interval: int):
        while self.is_connected:
            await asyncio.sleep(interval)
            try:
                await self.write_tcp("#ping", verbose=False)
            except Exception as e:
                logging.warning(f"{self.name} - [PERIODIC PING ERROR] {e}")
