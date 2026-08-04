from smartx_rfid.schemas.tag import TagSchema
import logging
import re


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

        # Quebra o payload em comandos por CR/LF e processa cada segmento.
        # Além disso, se '#' aparecer no meio do segmento, transforma cada
        # ocorrência em um novo comando (preservando o '#').
        chunks = re.split(r"[\r\n]+", data)
        for chunk in chunks:
            if not chunk:
                continue
            parts = re.split(r"(?=#)", chunk)
            for part in parts:
                cmd = part.strip()
                if not cmd:
                    continue
                self._process_single_command(cmd, verbose)

    def on_start(self):
        """Called when reader starts reading tags."""
        self.is_reading = True
        self.clear_tags()

    def on_stop(self):
        """Called when reader stops reading tags."""
        self.is_reading = False

    def on_tag(self, tag: dict):
        """Process detected RFID tag data.

        Args:
            tag: Tag information dictionary
        """
        try:
            tag_data = TagSchema(**tag)
            tag = tag_data.model_dump()
            self.emit_event("tag", tag)
        except Exception as e:
            logging.error(f"{self.name} - Invalid tag data: {e}")

    def _process_single_command(self, data: str, verbose: bool = False):
        """Processa um único comando (sem CR/LF dentro).

        Faz correspondência case-insensitive nos prefixes, preservando
        o payload depois de ':' (por exemplo serial numbers).
        """
        raw = data
        lower = raw.lower()

        if raw == "" or lower == "#pong":
            return

        if verbose:
            try:
                self.emit_event("receive", raw)
            except Exception:
                pass

        if lower.startswith("#read:"):
            after = raw.split(":", 1)[1].strip().lower()
            if after.endswith("on"):
                self.on_start()
            else:
                self.on_stop()

        elif lower.startswith("#t+@"):
            tag = raw[4:]
            parts = tag.split("|")
            epc = parts[0].lower() if len(parts) > 0 and parts[0] != "" else None
            tid = parts[1].lower() if len(parts) > 1 and parts[1] != "" else None
            ant = parts[2] if len(parts) > 2 and parts[2] != "" else 0
            rssi = parts[3] if len(parts) > 3 and parts[3] != "" else 0
            protected = parts[4] if len(parts) > 4 else None
            try:
                ant_i = int(ant)
            except Exception:
                ant_i = 0
            try:
                rssi_i = int(rssi) * (-1)
            except Exception:
                rssi_i = 0
            current_tag = {"epc": epc, "tid": tid, "ant": int(ant_i), "rssi": int(rssi_i), "protected": protected}
            self.on_tag(current_tag)

        elif lower == "#tags_cleared":
            try:
                self.emit_event("tags_cleared", True)
            except Exception:
                pass

        elif lower == "#setup_done":
            try:
                self.emit_event("setup_done", True)
            except Exception:
                pass

        elif lower.startswith("#name:"):
            _, serial = raw.split(":", 1)
            self.serial_number = serial.strip()
            try:
                self.emit_event("serial_number", self.serial_number)
            except Exception:
                pass

        else:
            try:
                self.emit_event("receive", raw)
            except Exception:
                pass
