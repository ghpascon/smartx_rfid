import asyncio
import json
import logging

import httpx


class ReaderHelpers:
    """Helper methods for R700 reader management."""

    async def check_firmware_version(self, session: httpx.AsyncClient | None = None):
        """Check if reader firmware version is compatible.

        Args:
            session: HTTP session to use

        Returns:
            bool: True if firmware is compatible
        """
        endpoint = self.check_version_endpoint

        try:
            if session is None:
                async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=5.0) as client:
                    response = await client.get(endpoint)
            else:
                response = await session.get(endpoint)

            if response.status_code != 200:
                logging.warning(f"{self.name} - Failed to get firmware version: {response.status_code}")
                return False

            if not self.firmware_version:
                return True

            version_info = response.json()
            firmware_version = version_info.get("primaryFirmware", "Unknown")
            return firmware_version.startswith(self.firmware_version)

        except Exception as e:
            logging.warning(f"{self.name} - Error GET {endpoint}: {e}")
            return False

    async def configure_interface(self, session):
        return await self.post_to_reader(
            session,
            self.endpoint_interface,
            payload=self.interface_config,
            method="put",
            retries=2,
            retry_delay=0.25,
        )

    async def start_inventory(self, check_gpi=True):
        """Public method to start inventory with concurrency control."""
        if not self.is_connected:
            logging.warning(f"{self.name} - Cannot start inventory: not connected")
            return False
        if self.is_gpi_trigger_on and check_gpi:
            logging.info(f"{self.name} - Cannot start inventory: GPI trigger is on")
            return False

        async with self._command_lock:
            if self._session is not None and not self._session.is_closed:
                success = await self._start_inventory(self._session)
                if success:
                    self.is_reading = True
                return success
            else:
                logging.warning(f"{self.name} - Cannot start inventory: session is closed")
                return False

    async def stop_inventory(self, check_gpi=True):
        """Public method to stop inventory with concurrency control."""
        if not self.is_connected:
            logging.warning(f"{self.name} - Cannot stop inventory: not connected")
            return False
        if self.is_gpi_trigger_on and check_gpi:
            logging.info(f"{self.name} - Cannot stop inventory: GPI trigger is on")
            return False

        async with self._command_lock:
            if self._session is not None and not self._session.is_closed:
                success = await self._stop_inventory(self._session)
                if success:
                    self.is_reading = False
                return success
            else:
                logging.warning(f"{self.name} - Cannot stop inventory: session is closed")
                return False

    async def get_reader_status(self, session=None):
        try:
            if session is None:
                async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=5.0) as client:
                    response = await client.get(self.endpoint_status)
            else:
                response = await session.get(self.endpoint_status)
            if response.status_code != 200:
                logging.warning(f"{self.name} - Failed to get reader status: {response.status_code}")
                return None

            return response.json()
        except Exception as e:
            logging.error(f"{self.name} - Error getting reader status: {e}")
            return None

    async def _stop_inventory(self, session=None):
        # Check if any inventory is running
        results = await self.get_reader_status(session=session)
        if results is not None and results.get("status") == "idle":
            return True
        return await self.post_to_reader(session, self.endpoint_stop, timeout=5, retries=2, retry_delay=0.25)

    async def _start_inventory(self, session=None):
        return await self.post_to_reader(
            session, self.endpoint_start, payload=self.reading_config, retries=2, retry_delay=0.25
        )

    async def post_to_reader(
        self,
        session,
        endpoint,
        payload=None,
        method="post",
        timeout=3,
        retries: int = 0,
        retry_delay: float = 0.2,
        retry_backoff: float = 2.0,
        retry_on_status: tuple[int, ...] = (409, 429, 500, 502, 503, 504),
    ):
        if session is None:
            async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=timeout) as client:
                return await self.post_to_reader(
                    client,
                    endpoint,
                    payload,
                    method,
                    timeout,
                    retries=retries,
                    retry_delay=retry_delay,
                    retry_backoff=retry_backoff,
                    retry_on_status=retry_on_status,
                )

        method = method.lower()
        if method not in {"post", "put"}:
            logging.warning(f"{self.name} - Unsupported HTTP method for endpoint {endpoint}: {method}")
            return False

        attempts = max(1, retries + 1)
        delay = max(0.0, retry_delay)

        for attempt in range(1, attempts + 1):
            try:
                if method == "post":
                    response = await session.post(endpoint, json=payload, timeout=timeout)
                else:
                    response = await session.put(endpoint, json=payload, timeout=timeout)

                if 200 <= response.status_code < 300:
                    return True

                response_preview = (response.text or "")[:200]
                will_retry = attempt < attempts and response.status_code in retry_on_status
                logging.warning(
                    f"{self.name} - {method.upper()} {endpoint} failed: "
                    f"status={response.status_code}, attempt={attempt}/{attempts}, "
                    f"retry={will_retry}, response={response_preview}"
                )

                if will_retry:
                    if delay > 0:
                        await asyncio.sleep(delay)
                        delay *= retry_backoff
                    continue

                return False

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                will_retry = attempt < attempts
                logging.warning(
                    f"{self.name} - {method.upper()} {endpoint} transport error "
                    f"attempt={attempt}/{attempts}, retry={will_retry}: {exc}"
                )

                if will_retry:
                    if delay > 0:
                        await asyncio.sleep(delay)
                        delay *= retry_backoff
                    continue

                return False

            except Exception as exc:
                logging.warning(
                    f"{self.name} - {method.upper()} {endpoint} unexpected error attempt={attempt}/{attempts}: {exc}"
                )
                return False

        return False

    async def get_tag_list(self, session):
        """Stream tag data from reader. Blocks until connection is lost or stopped."""
        try:
            async with session.stream("GET", self.endpointDataStream, timeout=None) as response:
                if response.status_code != 200:
                    logging.warning(f"{self.name} - Failed to connect to data stream: {response.status_code}")
                    return

                logging.info(f"{self.name} - Connected to data stream.")

                async for line in response.aiter_lines():
                    # Verificar se deve parar a conexão
                    if self._stop_connection:
                        logging.info(f"{self.name} - Stopping data stream (disconnect requested)")
                        break

                    try:
                        string = line.strip()
                        if not string:
                            continue
                        jsonEvent = json.loads(string)

                        if "inventoryStatusEvent" in jsonEvent:
                            status = jsonEvent["inventoryStatusEvent"]["inventoryStatus"]
                            if status == "running":
                                if hasattr(self, "create_task"):
                                    self.create_task(self.on_start())
                                else:
                                    asyncio.create_task(self.on_start())
                            else:
                                if hasattr(self, "create_task"):
                                    self.create_task(self.on_stop())
                                else:
                                    asyncio.create_task(self.on_stop())
                        elif "tagInventoryEvent" in jsonEvent:
                            tagEvent = jsonEvent["tagInventoryEvent"]
                            if hasattr(self, "create_task"):
                                self.create_task(self.on_tag(tagEvent))
                            else:
                                asyncio.create_task(self.on_tag(tagEvent))

                    except (json.JSONDecodeError, UnicodeDecodeError) as parse_error:
                        logging.warning(f"{self.name} - Failed to parse event: {parse_error}")
        except httpx.ReadTimeout:
            logging.warning(f"{self.name} - Data stream read timeout")
        except httpx.RemoteProtocolError as e:
            logging.warning(f"{self.name} - Connection closed by reader: {e}")
        except Exception as e:
            logging.warning(f"{self.name} - Data stream error: {e}")
        finally:
            logging.info(f"{self.name} - Data stream ended")
            # Se não foi uma desconexão intencional, marcar como desconectado
            if not self._stop_connection:
                self.is_connected = False

    def get_gpo_command(
        self, pin: int = 1, state: bool | str = True, control: str = "static", time: int = 1000
    ) -> dict:
        """
        Gera o payload de configuração de GPO para o leitor RFID.

        Args:
            pin (int): Número do pino GPO a ser configurado. Default é 1.
            state (bool | str): Estado do pino. Pode ser:
                - True ou "high" → alto
                - False ou "low" → baixo
            control ("static" | "pulsed"): Tipo de controle do pino.
                - "static": mantém o estado
                - "pulsed": envia pulso por tempo definido
            time (int): Duração do pulso em milissegundos. Apenas usado se control="pulsed". Default 1000ms.

        Returns:
            dict: Payload compatível com a API do leitor RFID para configurar GPO.

        Example:
            gpo_cmd = self.get_gpo_command(pin=2, state=True, control="pulsed", time=500)
        """
        # Normaliza o estado
        if state is True:
            state = "high"
        elif state is False:
            state = "low"
        else:
            state = str(state).strip().lower()
            if state not in {"high", "low"}:
                raise ValueError(f"Invalid GPO state '{state}'. Use True/False or 'high'/'low'.")

        control = str(control).strip().lower()
        if control == "pulse":
            control = "pulsed"
        if control not in {"static", "pulsed"}:
            raise ValueError(f"Invalid GPO control '{control}'. Use 'static' or 'pulsed'.")

        gpo_config: dict = {"gpo": pin, "state": state, "control": control}
        if control == "pulsed":
            gpo_config["pulseDurationMilliseconds"] = int(time)

        return {"gpoConfigurations": [gpo_config]}

    async def get_reader_info(self, session=None):
        """Request reader information like firmware version, serial number, etc."""
        endpoint = self.endpoint_info
        try:
            if session is None:
                async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=5.0) as client:
                    response = await client.get(endpoint)
            else:
                response = await session.get(endpoint)

            if response.status_code != 200:
                logging.warning(f"{self.name} - Failed to get reader info: {response.status_code}")
                return None

            info = response.json()
            self.serial_number = info.get("serialNumber")
            self.emit_event("serial_number", self.serial_number)

            logging.info(f"{self.name} - Reader Serial Number: {self.serial_number}")
            return info

        except Exception as e:
            logging.warning(f"{self.name} - Error GET {endpoint}: {e}")
            return None
