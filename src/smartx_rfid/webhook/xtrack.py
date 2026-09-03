import logging
import httpx
import asyncio
from typing import List, Optional


class WebhookXtrack:
    def __init__(
        self,
        url: str,
        timeout: int = 5,
        batch_time: float = 3.0,
        queue_limit: int = 100,
    ):
        self.url = url
        self.timeout = timeout
        self.batch_time = batch_time
        self.queue_limit = queue_limit

        logging.info("WebhookXtrack init url=%s queue_limit=%s batch_time=%s", url, queue_limit, batch_time)

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
                resp = await client.post(
                    self.url,
                    content=payload,
                    headers={"Content-Type": "application/xml"},
                    timeout=self.timeout,
                )
                if resp.is_error:
                    logging.warning("post() returned error status=%s body=%s", resp.status_code, resp.text)
                else:
                    logging.debug("post() success status=%s body=%s", resp.status_code, resp.text)
        except Exception:
            logging.exception("Error in post()")

    async def add_to_queue(self, tag: dict):
        """
        Add a tag to the internal queue. The queue will be flushed when:
        - the queue reaches `queue_limit`
        - `batch_time` seconds elapse since the first queued item
        """
        need_send = False
        schedule_needed = False
        try:
            async with self._lock:
                self._queue.append(tag)
                qlen = len(self._queue)
                logging.debug(
                    "add_to_queue: appended tag epc=%s device=%s queue_len=%d", tag.get("epc"), tag.get("device"), qlen
                )
                need_send = qlen >= self.queue_limit
                schedule_needed = (self._send_task is None) or self._send_task.done()
                if need_send and self._send_task and not self._send_task.done():
                    # cancel pending timer if we'll send immediately
                    logging.debug("add_to_queue: cancelling pending timer because queue limit reached")
                    self._send_task.cancel()
                    self._send_task = None

            if need_send:
                logging.info("add_to_queue: queue limit reached (%d), sending batch now", self.queue_limit)
                await self._send_batch()
                return

            if schedule_needed:
                # start a background timer to flush after batch_time
                logging.debug("add_to_queue: scheduling batch timer for %.3fs", self.batch_time)
                self._send_task = asyncio.create_task(self._batch_timer())
        except Exception:
            logging.exception("Error in add_to_queue")

    def enqueue(self, tag: dict):
        """
        Convenience synchronous-friendly helper to schedule adding a tag.
        If called from an async context it schedules add_to_queue as a task.
        If no event loop is running it will run add_to_queue synchronously.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # no running loop in this thread; run synchronously
            logging.debug("enqueue: no running loop, running add_to_queue via asyncio.run")
            try:
                asyncio.run(self.add_to_queue(tag))
            except Exception:
                logging.exception("enqueue: failed running add_to_queue synchronously")
            return

        # schedule as a background task in the running loop
        try:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.add_to_queue(tag)))
            logging.debug("enqueue: scheduled add_to_queue in running loop")
        except Exception:
            logging.exception("enqueue: failed scheduling add_to_queue in loop")

    async def _batch_timer(self):
        try:
            logging.debug("_batch_timer: sleeping for %.3f seconds", self.batch_time)
            await asyncio.sleep(self.batch_time)
            logging.debug("_batch_timer: time elapsed, sending batch")
            await self._send_batch()
        except asyncio.CancelledError:
            # timer was cancelled because of an immediate send
            return
        except Exception:
            logging.exception("Error in _batch_timer")
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
            logging.info("_send_batch: sending %d items", len(items))
            parts = ["<msg>", "  <command>ReportReadEx</command>"]
            for tag in items:
                device = tag.get("device", "unknown")
                ant = tag.get("ant", "1")
                epc = tag.get("epc")
                if epc is None:
                    logging.debug("_send_batch: skipping tag without epc: %r", tag)
                    continue
                parts.append("  <data>")
                parts.append(f"    <param>EVENT=|DEVICENAME={device}|ANTENNANAME={ant}|TAGID={epc}|</param>")
                parts.append("    <compl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|DATA6=|</compl>")
                parts.append("  </data>")
            parts.append("</msg>")
            payload = "\n".join(parts)
            logging.debug("_send_batch: payload length=%d", len(payload))

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.url,
                    content=payload,
                    headers={"Content-Type": "application/xml"},
                    timeout=self.timeout,
                )
                if resp.is_error:
                    logging.warning("_send_batch: post returned status=%s body=%s", resp.status_code, resp.text)
                else:
                    logging.info("_send_batch: post success status=%s", resp.status_code)
        except Exception:
            logging.exception("Error in _send_batch")
