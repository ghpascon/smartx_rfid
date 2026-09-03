import logging
import httpx
import asyncio
from typing import List, Optional


class WebhookXtrack:
    def __init__(
        self,
        url: str,
        timeout: int = 5,
        batch_size: int = 10,
        batch_time: float = 2.5,
        queue_limit: int = 100,
    ):
        self.url = url
        self.timeout = timeout
        self.batch_size = batch_size
        self.batch_time = batch_time
        self.queue_limit = queue_limit

        # internal queue and synchronization
        self._queue: List[dict] = []
        self._lock = asyncio.Lock()
        self._send_task: Optional[asyncio.Task] = None

    async def post(self, tag: dict):
        """Send a single tag using the legacy ReportRead format."""
        try:
            device = tag.get("device", "unknown")
            ant = tag.get("ant", "1")
            epc = tag.get("epc", None)
            if epc is None:
                raise Exception("EPC is required")
            payload = f"""<msg>
                        <command>ReportRead</command>
                        <data>EVENT=|DEVICENAME={device}|ANTENNANAME={ant}|TAGID={epc}|</data>
                        <cmpl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|</cmpl>
                        </msg>"""
            async with httpx.AsyncClient() as client:
                await client.post(
                    self.url,
                    content=payload,
                    headers={"Content-Type": "application/xml"},
                    timeout=self.timeout,
                )
        except Exception as e:
            logging.info(f"Error Xtrack: {e}")

    async def add_to_queue(self, tag: dict):
        """
        Add a tag to the internal queue. The queue will be flushed when:
        - the queue reaches `queue_limit`
        - the queue reaches `batch_size`
        - `batch_time` seconds elapse since the first queued item
        """
        need_send = False
        schedule_needed = False
        try:
            async with self._lock:
                self._queue.append(tag)
                qlen = len(self._queue)
                need_send = qlen >= self.queue_limit or qlen >= self.batch_size
                schedule_needed = (self._send_task is None) or self._send_task.done()
                if need_send and self._send_task and not self._send_task.done():
                    # cancel pending timer if we'll send immediately
                    self._send_task.cancel()
                    self._send_task = None

            if need_send:
                await self._send_batch()
                return

            if schedule_needed:
                # start a background timer to flush after batch_time
                self._send_task = asyncio.create_task(self._batch_timer())
        except Exception as e:
            logging.info(f"Error Xtrack add_to_queue: {e}")

    async def _batch_timer(self):
        try:
            await asyncio.sleep(self.batch_time)
            await self._send_batch()
        except asyncio.CancelledError:
            # timer was cancelled because of an immediate send
            return
        except Exception as e:
            logging.info(f"Error Xtrack batch timer: {e}")
        finally:
            self._send_task = None

    async def _send_batch(self):
        # move queued items out under lock to minimize locked time
        async with self._lock:
            if not self._queue:
                return
            items = list(self._queue)
            self._queue.clear()
            if self._send_task and not self._send_task.done():
                self._send_task.cancel()
                self._send_task = None

        # build ReportReadEx payload with multiple <data> entries
        try:
            parts = ["<msg>", "  <command>ReportReadEx</command>"]
            for tag in items:
                device = tag.get("device", "unknown")
                ant = tag.get("ant", "1")
                epc = tag.get("epc")
                if epc is None:
                    continue
                parts.append("  <data>")
                parts.append(f"    <param>EVENT=|DEVICENAME={device}|ANTENNANAME={ant}|TAGID={epc}|</param>")
                parts.append("    <compl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|DATA6=|</compl>")
                parts.append("  </data>")
            parts.append("</msg>")
            payload = "\n".join(parts)

            async with httpx.AsyncClient() as client:
                await client.post(
                    self.url,
                    content=payload,
                    headers={"Content-Type": "application/xml"},
                    timeout=self.timeout,
                )
        except Exception as e:
            logging.info(f"Error Xtrack send_batch: {e}")
