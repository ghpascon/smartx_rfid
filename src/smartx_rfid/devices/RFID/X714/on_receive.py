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
            self.is_reading = data.endswith("on")
            if self.is_reading:
                self.on_start()
            else:
                self.on_stop()

        elif data.startswith("#t+@"):
            tag = data[4:]
            epc, tid, ant, rssi = tag.split("|")
            current_tag = {
                "epc": epc,
                "tid": tid,
                "ant": int(ant),
                "rssi": int(rssi) * (-1),
            }
            self.on_tag(current_tag)

        elif len(data) == 24:
            self.on_tag(data)

        elif data.startswith("#set_cmd:"):
            logging.info(f"{self.name} - CONFIG -> {data[data.index(':') + 1 :]}")

        elif data == "#tags_cleared":
            self.on_event(self.name, "tags_cleared", True)

    def on_start(self):
        """Called when reader starts reading tags."""
        self.clear_tags()
        self.on_event(self.name, "reading", True)

    def on_stop(self):
        """Called when reader stops reading tags."""
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
