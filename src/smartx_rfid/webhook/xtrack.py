import logging
import httpx
import asyncio
import time
from typing import List, Optional
from xml.sax.saxutils import escape


class WebhookXtrack:
    def __init__(
        self,
        url: str,
        timeout: float = 5,
        batch_time: float = 3.0,
        queue_limit: int = 100,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        max_queue_size: int = 5000,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        pool_timeout: Optional[float] = None,
    ):
        self.url = url
        self.timeout = float(timeout)
        self.batch_time = batch_time
        self.queue_limit = queue_limit
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))
        self.max_queue_size = max(queue_limit, int(max_queue_size))

        self._http_timeout = httpx.Timeout(
            timeout=self.timeout,
            connect=self.timeout if connect_timeout is None else float(connect_timeout),
            read=self.timeout if read_timeout is None else float(read_timeout),
            write=self.timeout if write_timeout is None else float(write_timeout),
            pool=self.timeout if pool_timeout is None else float(pool_timeout),
        )

        logging.info(
            "WebhookXtrack init url=%s queue_limit=%s batch_time=%.3fs timeout=%.2fs retries=%d max_queue_size=%d",
            url,
            queue_limit,
            batch_time,
            self.timeout,
            self.max_retries,
            self.max_queue_size,
        )

        # internal queue and synchronization
        self._queue: List[dict] = []
        self._lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._send_task: Optional[asyncio.Task] = None
        self._dropped_count = 0

    @staticmethod
    def _response_is_error(resp) -> bool:
        is_error = getattr(resp, "is_error", None)
        if is_error is not None:
            return bool(is_error)

        status_code = getattr(resp, "status_code", None)
        if status_code is None:
            return True
        return int(status_code) >= 400

    @staticmethod
    def _response_text(resp) -> str:
        text = getattr(resp, "text", None)
        if text is None:
            return ""
        return str(text)

    @staticmethod
    def _build_event_param(device: str, ant: str, epc: str) -> str:
        return f"EVENT=|DEVICENAME={escape(str(device))}|ANTENNANAME={escape(str(ant))}|TAGID={escape(str(epc))}|"

    def _schedule_batch_timer_locked(self):
        if self._send_task is None or self._send_task.done():
            self._send_task = asyncio.create_task(self._batch_timer())
            logging.debug("_schedule_batch_timer_locked: timer scheduled for %.3fs", self.batch_time)

    def _cancel_batch_timer_locked(self, reason: str, current_task: Optional[asyncio.Task] = None):
        if self._send_task is None:
            return

        if current_task is not None and self._send_task is current_task:
            # Never cancel the currently running timer task from inside itself.
            logging.debug("_cancel_batch_timer_locked: skipping self-cancel reason=%s", reason)
            self._send_task = None
            return

        if not self._send_task.done():
            logging.debug("_cancel_batch_timer_locked: cancelling timer reason=%s", reason)
            self._send_task.cancel()
        self._send_task = None

    async def _post_payload(self, payload: str, origin: str, item_count: int) -> bool:
        max_attempts = self.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            started_at = time.perf_counter()
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        self.url,
                        content=payload,
                        headers={"Content-Type": "application/xml"},
                        timeout=self._http_timeout,
                    )

                elapsed_ms = (time.perf_counter() - started_at) * 1000
                status_code = getattr(resp, "status_code", "unknown")
                if self._response_is_error(resp):
                    logging.warning(
                        "%s: HTTP error status=%s attempt=%d/%d elapsed_ms=%.2f items=%d body=%s",
                        origin,
                        status_code,
                        attempt,
                        max_attempts,
                        elapsed_ms,
                        item_count,
                        self._response_text(resp),
                    )
                else:
                    logging.info(
                        "%s: success status=%s attempt=%d/%d elapsed_ms=%.2f items=%d",
                        origin,
                        status_code,
                        attempt,
                        max_attempts,
                        elapsed_ms,
                        item_count,
                    )
                    return True
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                logging.warning(
                    "%s: network/timeout error attempt=%d/%d elapsed_ms=%.2f items=%d error=%s",
                    origin,
                    attempt,
                    max_attempts,
                    elapsed_ms,
                    item_count,
                    exc,
                )
            except Exception:
                logging.exception(
                    "%s: unexpected error attempt=%d/%d items=%d", origin, attempt, max_attempts, item_count
                )

            if attempt < max_attempts:
                backoff = self.retry_backoff * attempt
                logging.info("%s: retrying in %.2fs (attempt %d/%d)", origin, backoff, attempt + 1, max_attempts)
                await asyncio.sleep(backoff)

        logging.error("%s: failed after %d attempts items=%d", origin, max_attempts, item_count)
        return False

    async def post(self, tag: dict):
        """Send a single tag using the legacy ReportRead format."""
        try:
            device = tag.get("device", "unknown")
            ant = tag.get("ant", "1")
            epc = tag.get("epc", None)
            if epc is None:
                raise Exception("EPC is required")
            event = self._build_event_param(device, ant, epc)
            payload = f"""<msg>
                        <command>ReportRead</command>
                        <data>{event}</data>
                        <cmpl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|</cmpl>
                        </msg>"""
            await self._post_payload(payload=payload, origin="post", item_count=1)
        except Exception:
            logging.exception("Error in post()")

    async def add_to_queue(self, tag: dict):
        """
        Add a tag to the internal queue. The queue will be flushed when:
        - the queue reaches `queue_limit`
        - `batch_time` seconds elapse since the first queued item
        """
        need_send = False
        try:
            if not isinstance(tag, dict):
                logging.warning("add_to_queue: ignoring non-dict tag type=%s", type(tag).__name__)
                return

            async with self._lock:
                if len(self._queue) >= self.max_queue_size:
                    dropped = self._queue.pop(0)
                    self._dropped_count += 1
                    logging.warning(
                        "add_to_queue: queue full (%d), dropping oldest epc=%s dropped_total=%d",
                        self.max_queue_size,
                        dropped.get("epc"),
                        self._dropped_count,
                    )

                self._queue.append(tag)
                qlen = len(self._queue)
                logging.debug(
                    "add_to_queue: appended tag epc=%s device=%s queue_len=%d", tag.get("epc"), tag.get("device"), qlen
                )
                need_send = qlen >= self.queue_limit

                if need_send and self._send_task and not self._send_task.done():
                    self._cancel_batch_timer_locked(reason="queue_limit reached")
                elif not need_send:
                    self._schedule_batch_timer_locked()

            if need_send:
                logging.info("add_to_queue: queue limit reached (%d), sending batch now", self.queue_limit)
                await self._send_batch(trigger="queue_limit")
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
        current_task = asyncio.current_task()
        try:
            logging.debug("_batch_timer: sleeping for %.3f seconds", self.batch_time)
            await asyncio.sleep(self.batch_time)
            logging.debug("_batch_timer: time elapsed, sending batch")
            await self._send_batch(trigger="batch_time")
        except asyncio.CancelledError:
            # timer was cancelled because of an immediate send
            logging.debug("_batch_timer: cancelled")
            return
        except Exception:
            logging.exception("Error in _batch_timer")
        finally:
            async with self._lock:
                if self._send_task is current_task:
                    self._send_task = None

    def _build_report_read_ex_payload(self, items: List[dict]):
        parts = ["<msg>", " <command>ReportReadEx</command>"]
        valid_items: List[dict] = []
        skipped_without_epc = 0

        for tag in items:
            device = tag.get("device", "unknown")
            ant = tag.get("ant", "1")
            epc = tag.get("epc")
            if epc is None:
                skipped_without_epc += 1
                continue

            event = self._build_event_param(device, ant, epc)
            valid_items.append(tag)
            parts.append(" <data>")
            parts.append(f"   <param>{event}</param>")
            parts.append("   <compl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|DATA6=|</compl>")
            parts.append(" </data>")

        parts.append("</msg>")
        return "\n".join(parts), valid_items, skipped_without_epc

    async def _send_batch(self, trigger: str = "manual"):
        items_to_requeue: List[dict] = []
        try:
            async with self._send_lock:
                current_task = asyncio.current_task()
                async with self._lock:
                    if not self._queue:
                        logging.debug("_send_batch: queue empty trigger=%s", trigger)
                        return
                    items = list(self._queue)
                    self._queue.clear()
                    items_to_requeue = list(items)
                    if self._send_task and not self._send_task.done():
                        self._cancel_batch_timer_locked(reason="send_started", current_task=current_task)

                payload, valid_items, skipped_without_epc = self._build_report_read_ex_payload(items)
                if skipped_without_epc:
                    logging.warning("_send_batch: skipped %d tags without epc", skipped_without_epc)

                if not valid_items:
                    logging.warning("_send_batch: nothing to send trigger=%s (all tags invalid)", trigger)
                    return

                items_to_requeue = list(valid_items)

                logging.info(
                    "_send_batch: trigger=%s total_items=%d valid_items=%d payload_length=%d",
                    trigger,
                    len(items),
                    len(valid_items),
                    len(payload),
                )

                success = await self._post_payload(payload=payload, origin="_send_batch", item_count=len(valid_items))
                if success:
                    return

                async with self._lock:
                    self._queue = valid_items + self._queue
                    logging.error(
                        "_send_batch: failed to send, requeued %d tags queue_len=%d",
                        len(valid_items),
                        len(self._queue),
                    )
                    self._schedule_batch_timer_locked()
        except Exception:
            logging.exception("Error in _send_batch")
            if items_to_requeue:
                async with self._lock:
                    self._queue = items_to_requeue + self._queue
                    logging.error(
                        "_send_batch: exception path, requeued %d tags queue_len=%d",
                        len(items_to_requeue),
                        len(self._queue),
                    )
                    self._schedule_batch_timer_locked()
