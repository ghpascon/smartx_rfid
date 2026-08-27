import logging
from typing_extensions import Literal
from smartx_rfid.schemas.tag import WriteTagValidator
import asyncio


class WriteCommands:
    """RFID tag write commands for X714."""

    async def write_epc(self, target_identifier: str | None, target_value: str | None, new_epc: str, password: str):
        """Write new EPC code to RFID tag.

        Args:
            target_identifier: How to find tag (epc, tid, user)
            target_value: Current tag value to match
            new_epc: New EPC code to write
            password: Tag access password
        """
        try:
            validated_tag = WriteTagValidator(
                target_identifier=target_identifier,
                target_value=target_value,
                new_epc=new_epc,
                password=password,
            )
        except Exception as e:
            logging.warning(f"{self.name} - {e}")
            return
        identifier = validated_tag.target_identifier
        value = validated_tag.target_value
        epc = validated_tag.new_epc
        password = validated_tag.password
        logging.info(f"{self.name} - Writing EPC: {epc} (Current: {identifier}={value})")
        if identifier is None:
            self.write(f"#WRITE:{epc};{password}", False)
        else:
            self.write(f"#WRITE:{epc};{password};{identifier};{value}", False)

    async def write_gpo(
        self, pin: int = 1, state: bool = True, control: Literal["static", "pulsed"] = "static", time: int = 1000
    ):
        if control not in ["static", "pulsed"]:
            logging.warning(f"{self.name} - Invalid control type: {control}")
            raise ValueError("Control must be 'static' or 'pulsed'")

        if pin < 0 or pin > 3:
            logging.warning(f"{self.name} - Invalid GPO pin: {pin}")
            raise ValueError("Pin must be between 0 and 3")

        if control == "static":
            command = f"#GPO:{pin},{'ON' if state else 'OFF'}"
            self.write(command)
            return

        self.emit_event("gpo", {"pin": pin, "state": state, "control": control, "time": time})

        cmd_1 = f"#GPO:{pin},{'ON' if state else 'OFF'}"
        cmd_2 = f"#GPO:{pin},{'OFF' if state else 'ON'}"
        self.write(cmd_1)
        await asyncio.sleep(time / 1000)
        self.write(cmd_2)
