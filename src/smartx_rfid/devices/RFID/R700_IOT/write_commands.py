import logging

import httpx


class WriteCommands:
    """RFID tag write commands for R700 reader."""

    def get_write_cmd(self, tag):
        """Generate write command for tag programming.

        Args:
            tag: Tag data with target and new EPC

        Returns:
            dict: Write command for R700 API
        """
        identifier = tag.target_identifier
        target = tag.target_value
        epc = tag.new_epc
        password = tag.password

        return {
            "accessCommands": [
                {
                    "identifier": "1",
                    "blockWrite": {
                        "memoryBank": "epc",
                        "wordOffset": 2,
                        "dataHex": epc[0:8],
                    },
                },
                {
                    "identifier": "2",
                    "blockWrite": {
                        "memoryBank": "epc",
                        "wordOffset": 4,
                        "dataHex": epc[8:16],
                    },
                },
                {
                    "identifier": "3",
                    "blockWrite": {
                        "memoryBank": "epc",
                        "wordOffset": 6,
                        "dataHex": epc[16:24],
                    },
                },
            ],
            "tagAccessPasswordHex": password,
            "tagSelectors": [
                {
                    "action": "include",
                    "tagMemoryBank": identifier if identifier else "epc",
                    "bitOffset": 0 if identifier == "tid" else 32,
                    "mask": target if target else "0",
                    "maskLength": 1 if identifier is None else 96,
                }
            ],
        }

    async def send_write_command(self, write_command):
        if not isinstance(write_command, list):
            write_command = [write_command]
        payload = {"accessConfigurations": write_command}
        try:
            async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=10.0) as session:
                await self.post_to_reader(session, self.endpoint_write, payload=payload)
        except Exception as e:
            logging.warning(f"{self.name} - Failed to Write: {e}")
