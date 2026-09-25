import asyncio
import logging
import re
from smartx_rfid.utils import get_hash


class Helpers:
    """Helper functions for TCP connection management."""

    def _split_hs_fields(self, cmd: str) -> list[str] | None:
        """Split one ~HS line into sanitized comma-separated fields."""
        if "," not in cmd:
            return None

        fields: list[str] = []
        for raw in cmd.split(","):
            # Keep only alphanumeric chars to strip STX/ETX/CR/LF wrappers.
            field = re.sub(r"[^a-zA-Z0-9]", "", raw)
            if field == "":
                continue
            fields.append(field)

        return fields or None

    def _build_status_from_hs(self, hs1: list[str], hs2: list[str]) -> dict[str, bool | str]:
        """Build semantic status flags from ~HS String 1 and String 2."""
        paper_out = hs1[1] == "1"
        paused = hs1[2] == "1"
        buffer_full = hs1[5] == "1"
        partial_format = hs1[7] == "1"
        corrupt_ram = hs1[9] == "1"
        under_temp = hs1[10] == "1"
        over_temp = hs1[11] == "1"

        head_up = hs2[2] == "1"
        ribbon_out = hs2[3] == "1"
        thermal_transfer = hs2[4] == "1"
        label_waiting = hs2[7] == "1"

        hard_error = paper_out or head_up or (thermal_transfer and ribbon_out) or over_temp or corrupt_ram

        can_print = not (hard_error or paused or buffer_full or partial_format or label_waiting)

        if paper_out:
            status = "error: paper_out"
        elif head_up:
            status = "error: head_open"
        elif thermal_transfer and ribbon_out:
            status = "error: ribbon_out"
        elif over_temp:
            status = "error: over_temp"
        elif corrupt_ram:
            status = "error: corrupt_ram"
        elif paused:
            status = "paused"
        elif buffer_full:
            status = "busy: receive_buffer_full"
        elif partial_format:
            status = "busy: partial_format"
        elif label_waiting:
            status = "waiting: peel_label_present"
        elif under_temp:
            status = "warning: under_temp"
        else:
            status = "ready"

        return {
            "status": status,
            "can_print": can_print,
            "hard_error": hard_error,
            "paper_out": paper_out,
            "paused": paused,
            "head_up": head_up,
            "ribbon_out": ribbon_out,
            "thermal_transfer": thermal_transfer,
            "buffer_full": buffer_full,
            "partial_format": partial_format,
            "label_waiting": label_waiting,
            "under_temp": under_temp,
            "over_temp": over_temp,
            "corrupt_ram": corrupt_ram,
            "hs1": ",".join(hs1),
            "hs2": ",".join(hs2),
        }

    async def get_status(self):
        """Check if TCP connection is still alive."""
        get_status_cmd = "~HS"

        while self.is_connected:
            await asyncio.sleep(0.5)
            if (self.writer and self.writer.is_closing()) or (self.reader and self.reader.at_eof()):
                self.is_connected = False
                break

            await self.write(get_status_cmd, verbose=False)
            if len(self._to_print) > 0 and self.can_print:
                zpl = self._to_print.pop(0)
                logging.info(f"{self.name} - Sending: ZPL ID: {get_hash(zpl)}, {len(self._to_print)} left.")
                status, msg = self.print(zpl)
                if not status:
                    self.emit_event("print_sent_error", msg)
                if status:
                    self.emit_event("print_sent", msg)

    async def receive_data(self):
        """Receive and process incoming TCP data."""
        buffer = ""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(self.reader.read(1024), timeout=0.1)
                except asyncio.TimeoutError:
                    # Timeout: process what's in the buffer as a command
                    if buffer:
                        await self.on_receive_cmd(buffer.strip())
                        buffer = ""
                    continue

                if not data:
                    raise ConnectionError("Connection lost")

                buffer += data.decode(errors="ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    # event received
                    await self.on_receive_cmd(line.strip())

        except Exception as e:
            self.is_connected = False
            logging.error(f"[RECEIVE ERROR] {e}")

    def clean_cmd(self, cmd: str) -> str:
        # remove tudo que não for letras ou números
        return re.sub(r"[^a-zA-Z0-9]", "", cmd).lower()

    async def on_receive_cmd(self, cmd: str):
        fields = self._split_hs_fields(cmd)
        if not fields:
            return

        if len(fields) == 12:
            self._hs_string_1 = fields
        elif len(fields) == 11:
            self._hs_string_2 = fields
        elif len(fields) == 2:
            self._hs_string_3 = fields
        else:
            return

        hs1 = getattr(self, "_hs_string_1", None)
        hs2 = getattr(self, "_hs_string_2", None)
        if not hs1 or not hs2:
            return

        parsed = self._build_status_from_hs(hs1, hs2)
        status = str(parsed["status"])
        can_print = bool(parsed["can_print"])
        hard_error = bool(parsed["hard_error"])

        if status == self.last_status and can_print == self.last_can_print and not self._print_sent:
            return

        self.can_print = can_print
        print_sent = False

        if self._print_sent and self.can_print:
            print_sent = True
            self.emit_event("print_success", f"{self._zpl_id}")
            self._print_sent = False
            self._zpl_id = None
        elif self._print_sent and hard_error:
            self.emit_event("print_error", f"{self._zpl_id}")
            self._print_sent = False
            self._zpl_id = None

        if status != self.last_status or self.can_print != self.last_can_print or print_sent:
            self.emit_event("status", status)

        # Update Last Status
        self.last_status = status
        self.last_can_print = self.can_print
