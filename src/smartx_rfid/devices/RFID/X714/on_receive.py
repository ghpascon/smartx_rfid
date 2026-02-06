from smartx_rfid.schemas.tag import TagSchema
import logging


class OnReceive:
    """Handle incoming data from X714 reader."""

    def on_receive(self, data, verbose: bool = False):
        """Process data received from reader.

        Args:
            data: Raw data from reader
            verbose: Show received data in logs
        """
        if not isinstance(data, str):
            data = data.decode(errors="ignore")
        data = data.replace("\r", "").replace("\n", "")
        data = data.lower()
        if verbose:
            self.on_event(self.name, "receive", data)

        if data.startswith("#read:"):
            self.on_start() if data.endswith("on") else self.on_stop()

        elif data.startswith("#t+@"):
            tag = data[4:]
            parts = tag.split("|")
            # parts: epc, tid, ant, rssi, protected (2 a 5 elementos)
            epc = parts[0] if len(parts) > 0 else None
            tid = parts[1] if len(parts) > 1 else None
            ant = parts[2] if len(parts) > 2 and parts[2] != "" else 0
            rssi = parts[3] if len(parts) > 3 and parts[3] != "" else 0
            protected = parts[4] if len(parts) > 4 else None
            current_tag = {"epc": epc, "tid": tid, "ant": int(ant), "rssi": int(rssi) * (-1), "protected": protected}
            self.on_tag(current_tag)

        elif data == "#tags_cleared":
            self.on_event(self.name, "tags_cleared", True)

        elif data == "#setup_done":
            self.on_event(self.name, "setup_done", True)

        # fallback
        else:
            self.on_event(self.name, "receive", data)

    def on_start(self):
        """Called when reader starts reading tags."""
        self.is_reading = True
        self.clear_tags()
        self.on_event(self.name, "reading", True)

    def on_stop(self):
        """Called when reader stops reading tags."""
        self.is_reading = False
        self.on_event(self.name, "reading", False)

    def on_tag(self, tag: dict):
        """Process detected RFID tag data.

        Args:
            tag: Tag information dictionary
        """
        """Process detected RFID tag data.
        
        Args:
            tag: Tag information dictionary
        """
        try:
            tag_data = TagSchema(**tag)
            tag = tag_data.model_dump()
            self.on_event(self.name, "tag", tag)
        except Exception as e:
            logging.error(f"{self.name} - Invalid tag data: {e}")
