import logging
from smartx_rfid.schemas.tag import WriteTagValidator


class WriteCommands:
    def write_epc(self, target_identifier: str | None, target_value: str | None, new_epc: str, password: str):
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
