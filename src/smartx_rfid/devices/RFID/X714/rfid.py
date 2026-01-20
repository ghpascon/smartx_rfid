import asyncio


class RfidCommands:
    """RFID reader control commands for X714."""

    async def start_inventory(self):
        """Start reading RFID tags."""
        self.write("#READ:ON")

    async def stop_inventory(self):
        """Stop reading RFID tags."""
        self.write("#READ:OFF")

    def clear_tags(self):
        """Clear all stored tags from memory."""
        self.write("#CLEAR")

    def config_reader(self):
        """Configure reader settings like antennas, session, etc."""
        # Start Reading
        if self.start_reading:
            asyncio.create_task(self.start_inventory())
        else:
            asyncio.create_task(self.stop_inventory())
            
        set_cmd = "#set_cmd:"

        # ANTENNAS
        antennas = self.ant_dict
        for antenna in antennas:
            ant = antennas.get(antenna)
            ant_cmd = f"|set_ant:{antenna},{ant.get('active')},{ant.get('power')},{abs(ant.get('rssi'))}"
            set_cmd += ant_cmd

        # SESSION
        set_cmd += f"|SESSION:{self.session}"

        # START_READING
        set_cmd += f"|START_READING:{self.start_reading}"
        if self.start_reading:
            self.is_reading = True

        # GPI_START
        set_cmd += f"|GPI_START:{self.gpi_start}"

        # IGNORE_READ
        set_cmd += f"|IGNORE_READ:{self.ignore_read}"

        # ALWAYS_SEND
        set_cmd += f"|ALWAYS_SEND:{self.always_send}"

        # SIMPLE_SEND
        set_cmd += f"|SIMPLE_SEND:{self.simple_send}"

        # KEYBOARD
        set_cmd += f"|KEYBOARD:{self.keyboard}"

        # BUZZER
        set_cmd += f"|BUZZER:{self.buzzer}"

        # DECODE_GTIN
        set_cmd += f"|DECODE_GTIN:{self.decode_gtin}"

        set_cmd = set_cmd.lower()
        set_cmd = set_cmd.replace("true", "on").replace("false", "off")
        self.write(set_cmd)

        # OTHER CONFIG
        self.write(f"#hotspot:{'on' if self.hotspot else 'off'}")
        self.write(f"#prefix:{self.prefix}")
        if self.protected_inventory_password is not None:
            self.write(f"#protected_inventory:on;{self.protected_inventory_password}")
        else:
            self.write("#protected_inventory:off")

    async def auto_clear(self):
        while True:
            await asyncio.sleep(30)
            if self.is_connected:
                self.clear_tags()
