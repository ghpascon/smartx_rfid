class OnEvent:
    """Handle R700 reader events."""
    
    async def on_start(self):
        """Called when reader starts reading tags."""
        self.is_reading = True
        self.on_event(self.name, "reading", True)

    async def on_stop(self):
        """Called when reader stops reading tags."""
        self.is_reading = False
        self.on_event(self.name, "reading", False)

    async def on_tag(self, tag):
        """Process detected RFID tag data.
        
        Args:
            tag: Raw tag data from reader API
        """
        current_tag = {
            "epc": tag.get("epcHex"),
            "tid": tag.get("tidHex"),
            "ant": tag.get("antennaPort"),
            "rssi": int(tag.get("peakRssiCdbm", 0) / 100),
        }
        self.on_event(self.name, "tag", current_tag)
