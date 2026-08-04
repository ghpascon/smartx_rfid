import asyncio
import logging
import re
from smartx_rfid.utils import get_hash


class Helpers:
    """Helper functions for TCP connection management."""

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
        cmd = self.clean_cmd(cmd)
        if len(cmd) < 22:
            return
        status = cmd[:5]
        if status == self.last_status and status != "00000":
            return
        # Update Last Status
        self.last_status = status

        self.can_print = False

        # Ready to print
        if status == "00000":
            self.can_print = True
            print_sent = False

            if self._print_sent:
                print_sent = True
                self.emit_event("print_success", f"{self._zpl_id}")
                self._print_sent = False
                self._zpl_id = None
            if not self.last_can_print or print_sent:
                self.emit_event("status", "ready")
        # error:
        elif status == "00001":
            if self._print_sent:
                self.emit_event("print_error", f"{self._zpl_id}")
                self._print_sent = False
                self._zpl_id = None
            self.emit_event("status", f"error: {status}")
        else:
            self.emit_event("status", status)

        self.last_can_print = self.can_print
