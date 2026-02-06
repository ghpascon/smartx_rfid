import asyncio


class RfidCommands:
    """RFID reader control commands for X714."""

    async def start_inventory(self):
        """Start reading RFID tags."""
        if self.is_gpi_trigger_on:
            return
        self.write("#READ:ON")
        self.on_start()

    async def stop_inventory(self):
        """Stop reading RFID tags."""
        if self.is_gpi_trigger_on:
            return
        self.write("#READ:OFF")
        self.on_stop()

    def clear_tags(self):
        """Clear all stored tags from memory."""
        self.write("#CLEAR")

    def config_reader(self):
        """Configure reader settings like antennas, session, etc."""
        cmds = []

        # ANTENNAS
        for antenna, ant in self.ant_dict.items():
            ant_cmd = f"#set_ant:{antenna},{ant.get('active')},{ant.get('power')},{abs(ant.get('rssi'))}"
            cmds.append(ant_cmd)

        # SESSION
        cmds.append(f"#session:{self.session}")

        # START_READING
        cmds.append(f"#start_reading:{'on' if self.start_reading else 'off'}")
        if self.start_reading:
            self.on_start()

        # GPI_START
        cmds.append(f"#gpi_start:{'on' if self.gpi_start else 'off'}")

        # IGNORE_READ (se existir no firmware)
        if hasattr(self, "ignore_read"):
            cmds.append(f"#ignore_read:{'on' if self.ignore_read else 'off'}")

        # ALWAYS_SEND
        cmds.append(f"#always_send:{'on' if self.always_send else 'off'}")

        # SIMPLE_SEND
        cmds.append(f"#simple_send:{'on' if self.simple_send else 'off'}")

        # KEYBOARD
        cmds.append(f"#keyboard:{'on' if self.keyboard else 'off'}")

        # BUZZER
        cmds.append(f"#buzzer:{'on' if self.buzzer else 'off'}")

        # DECODE_GTIN
        cmds.append(f"#decode_gtin:{'on' if self.decode_gtin else 'off'}")

        # HOTSPOT
        cmds.append(f"#hotspot:{'on' if self.hotspot else 'off'}")

        # PREFIX
        cmds.append(f"#prefix:{self.prefix}")

        # Envia todos os comandos juntos, separados por '|'
        for cmd in cmds:
            self.write(cmd)

        # PROTECTED INVENTORY
        self.protected_inventory(self.protected_inventory_active)

        # Start Reading
        if self.start_reading:
            asyncio.create_task(self.start_inventory())
        else:
            asyncio.create_task(self.stop_inventory())

    async def auto_clear(self):
        while getattr(self, "_running", True):
            await asyncio.sleep(30)
            if self.is_connected:
                self.clear_tags()

    def protected_inventory(self, active: bool, password: str = None):
        if active:
            pwd = password if password is not None else self.protected_inventory_password
            self.write(f"#protected_inventory:on;{pwd}")
        else:
            self.write("#protected_inventory:off")

    def protected_mode(self, epc: str, password: str = None, active: bool = True):
        pwd = password if password is not None else self.protected_inventory_password
        self.write(f"#protected_mode:{epc};{pwd};{'on' if active else 'off'}")
