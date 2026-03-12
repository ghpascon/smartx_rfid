import asyncio
import logging


class Helpers:
    """Helper functions for TCP connection management."""

    async def monitor_connection(self):
        """Check if TCP connection is still alive."""
        while self.is_connected:
            await asyncio.sleep(3)
            if (self.writer and self.writer.is_closing()) or (self.reader and self.reader.at_eof()):
                self.is_connected = False
                logging.info("[DISCONNECTED] Socket closed.")
                break

            await self.write("ping", verbose=False)

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
                        await self.on_received_cmd(buffer.strip())
                        buffer = ""
                    continue

                if not data:
                    raise ConnectionError("Connection lost")

                buffer += data.decode(errors="ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    # event received
                    self.on_event(self.name, "receive", line.strip())

        except Exception as e:
            self.is_connected = False
            logging.error(f"[RECEIVE ERROR] {e}")
