from smartx_rfid.schemas import TagSchema


class OnEvent:
    """Handle R700 reader events."""

    async def on_start(self):
        """Called when reader starts reading tags."""
        self.is_reading = True

    async def on_stop(self):
        """Called when reader stops reading tags."""
        self.is_reading = False

    async def on_tag(self, tag):
        """Process detected RFID tag data.

        Args:
            tag: Raw tag data from reader API
        """
        current_tag = TagSchema(
            epc=tag.get("epcHex"),
            tid=tag.get("tidHex"),
            ant=tag.get("antennaPort"),
            rssi=int(tag.get("peakRssiCdbm", 0) / 100),
            protected=self.is_protected_inventory_active,
        )
        self.emit_event("tag", current_tag.model_dump())
