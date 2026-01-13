import asyncio
import json
import logging

import httpx


class ReaderHelpers:
    async def check_firmware_version(self, session: httpx.AsyncClient | None = None):
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
        )

    async def stop_inventory(self, session=None):
        return await self.post_to_reader(session, self.endpoint_stop)

    async def start_inventory(self, session=None):
        return await self.post_to_reader(session, self.endpoint_start, payload=self.reading_config)

    async def post_to_reader(self, session, endpoint, payload=None, method="post", timeout=3):
        try:
            if session is None:
                async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=timeout) as client:
                    return await self.post_to_reader(client, endpoint, payload, method, timeout)

            if method == "post":
                response = await session.post(endpoint, json=payload, timeout=timeout)
                if response.status_code != 204:
                    logging.warning(f"{self.name} - POST {endpoint} failed: {response.status_code}")

            elif method == "put":
                response = await session.put(endpoint, json=payload, timeout=timeout)
                if response.status_code != 204:
                    logging.warning(f"{self.name} - PUT {endpoint} failed: {response.status_code}")

            return response.status_code == 204

        except Exception as e:
            logging.warning(f"{self.name} - Error posting to {endpoint}: {e}")
            return False

    async def get_tag_list(self, session):
        try:
            async with session.stream("GET", self.endpointDataStream, timeout=None) as response:
                if response.status_code != 200:
                    logging.warning(f"{self.name} - Failed to connect to data stream: {response.status_code}")
                    return

                logging.info(f"{self.name} - Connected to data stream.")

                async for line in response.aiter_lines():
                    try:
                        string = line.strip()
                        if not string:
                            continue
                        jsonEvent = json.loads(string)

                        if "inventoryStatusEvent" in jsonEvent:
                            status = jsonEvent["inventoryStatusEvent"]["inventoryStatus"]
                            if status == "running":
                                asyncio.create_task(self.on_start())
                            else:
                                asyncio.create_task(self.on_stop())
                        elif "tagInventoryEvent" in jsonEvent:
                            tagEvent = jsonEvent["tagInventoryEvent"]
                            asyncio.create_task(self.on_tag(tagEvent))

                    except (json.JSONDecodeError, UnicodeDecodeError) as parse_error:
                        logging.warning(f"{self.name} - Failed to parse event: {parse_error}")
        except Exception as e:
            logging.warning(f"{self.name} - Unexpected error: {e}")

    async def get_gpo_command(
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
            gpo_cmd = await self.get_gpo_command(pin=2, state=True, control="pulsed", time=500)
        """
        # Normaliza o estado
        state = "high" if state is True else "low" if state is False else str(state)

        if control == "static":
            gpo_command = {"gpoConfigurations": [{"gpo": pin, "state": state, "control": control}]}
        elif control == "pulsed":
            gpo_command = {
                "gpoConfigurations": [
                    {
                        "gpo": pin,
                        "state": state,
                        "pulseDurationMilliseconds": time,
                        "control": control,
                    }
                ]
            }
        return gpo_command
