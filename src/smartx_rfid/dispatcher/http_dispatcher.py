import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import orjson


logger = logging.getLogger(__name__)


_STOP = object()


@dataclass(slots=True)
class _PostItem:
    source: str
    batch_size: int
    allow_batches: bool
    retry_attempts: int
    backoff_seconds: float
    flush_interval_seconds: float
    url: str
    headers: dict[str, Any] | None
    body: Any
    queued_at: float


@dataclass(slots=True, frozen=True)
class _PostBatchKey:
    source: str
    url: str
    headers_json: str
    batch_size: int
    allow_batches: bool
    flush_interval_seconds: float
    retry_attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class _PostEnvelope:
    key: _PostBatchKey
    items: list[_PostItem]
    queued_at: float


class HttpDispatcher:
    """
    Manages all HTTP POST dispatch operations.
    Batching is opt-in per dispatch (``allow_batches`` field in JSON config).

    Parameters
    ----------
    batch_size : int
            Max items per batched request (default 1000).
    flush_interval_seconds : float
            How often to flush pending batches (default 0.1).
    sender_workers : int
            Concurrent HTTP sender coroutines (default 64).
    queue_max_size : int
            Max items in internal queues (default 10_000).
    connect_timeout_seconds : float
            TCP connection timeout (default 2.0).
    read_timeout_seconds : float
            HTTP read/write timeout (default 5.0).
    pool_timeout_seconds : float
            Connection pool acquisition timeout (default 2.0).
    max_connections : int
            Max total HTTP connections in the pool (default 500).
    max_keepalive_connections : int
            Max keepalive connections (default 500).
    http2_enabled : bool
            Enable HTTP/2 (default True).
    """

    def __init__(
        self,
        batch_size: int = 1000,
        flush_interval_seconds: float = 0.1,
        sender_workers: int = 64,
        queue_max_size: int = 10_000,
        connect_timeout_seconds: float = 2.0,
        read_timeout_seconds: float = 5.0,
        pool_timeout_seconds: float = 2.0,
        max_connections: int = 500,
        max_keepalive_connections: int = 500,
        http2_enabled: bool = True,
    ) -> None:
        self.batch_size = max(1, batch_size)
        self.flush_interval_seconds = max(0.001, flush_interval_seconds)
        self.sender_workers = max(1, sender_workers)
        self.queue_max_size = max(1, queue_max_size)
        self.connect_timeout_seconds = max(0.1, connect_timeout_seconds)
        self.read_timeout_seconds = max(0.1, read_timeout_seconds)
        self.pool_timeout_seconds = max(0.1, pool_timeout_seconds)
        self.max_connections = max(1, max_connections)
        self.max_keepalive_connections = max(1, max_keepalive_connections)
        self.http2_enabled = http2_enabled

        self._batch_queue: asyncio.Queue[_PostItem | object] = asyncio.Queue(maxsize=self.queue_max_size)
        self._send_queue: asyncio.Queue[_PostEnvelope | object] = asyncio.Queue(maxsize=self.queue_max_size)
        self._batches: dict[_PostBatchKey, list[_PostItem]] = {}
        self._batch_task: asyncio.Task | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._client: httpx.AsyncClient | None = None

    def start(self) -> None:
        if self._client is None:
            self._client = self._make_client()
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._batch_loop(), name="http-dispatcher-batcher")
        if not self._worker_tasks:
            self._worker_tasks = [
                asyncio.create_task(self._sender_loop(i + 1), name=f"http-dispatcher-sender-{i + 1}")
                for i in range(self.sender_workers)
            ]
        logger.debug(
            "HttpDispatcher started | batch_size=%d flush_interval=%.3fs sender_workers=%d",
            self.batch_size,
            self.flush_interval_seconds,
            self.sender_workers,
        )

    async def stop(self, drain: bool = True) -> None:
        if drain:
            await self._batch_queue.join()
            await self._flush_all()
            await self._send_queue.join()

        if self._batch_task:
            await self._batch_queue.put(_STOP)
            await asyncio.gather(self._batch_task, return_exceptions=True)
            self._batch_task = None

        for _ in self._worker_tasks:
            await self._send_queue.put(_STOP)
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.debug("HttpDispatcher stopped")

    async def flush(self) -> None:
        await self._batch_queue.join()
        await self._flush_all()
        await self._send_queue.join()

    async def enqueue(self, item: _PostItem) -> None:
        try:
            self._batch_queue.put_nowait(item)
        except asyncio.QueueFull:
            await asyncio.wait_for(self._batch_queue.put(item), timeout=0.2)

    def _make_client(self) -> httpx.AsyncClient:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.connect_timeout_seconds,
                read=self.read_timeout_seconds,
                write=self.read_timeout_seconds,
                pool=self.pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=self.max_keepalive_connections,
                max_connections=self.max_connections,
                keepalive_expiry=60.0,
            ),
            http2=self.http2_enabled,
        )

    def _make_key(self, item: _PostItem) -> _PostBatchKey:
        return _PostBatchKey(
            source=item.source,
            url=item.url,
            headers_json=orjson.dumps(item.headers or {}, option=orjson.OPT_SORT_KEYS).decode(),
            batch_size=item.batch_size,
            allow_batches=item.allow_batches,
            flush_interval_seconds=item.flush_interval_seconds,
            retry_attempts=item.retry_attempts,
            backoff_seconds=item.backoff_seconds,
        )

    async def _batch_loop(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(self._batch_queue.get(), timeout=self._next_timeout())
            except TimeoutError:
                await self._flush_due()
                continue

            if item is _STOP:
                self._batch_queue.task_done()
                await self._flush_all()
                return

            assert isinstance(item, _PostItem)
            key = self._make_key(item)
            batch = self._batches.setdefault(key, [])
            batch.append(item)
            self._batch_queue.task_done()

            if not item.allow_batches or len(batch) >= item.batch_size:
                await self._flush_batch(key)
            else:
                await self._flush_due()

    async def _flush_due(self) -> None:
        if not self._batches:
            return
        now = time.monotonic()
        for key, batch in list(self._batches.items()):
            if not batch:
                continue
            oldest = batch[0].queued_at
            if now - oldest >= key.flush_interval_seconds:
                await self._flush_batch(key)

    def _next_timeout(self) -> float:
        if not self._batches:
            return self.flush_interval_seconds
        now = time.monotonic()
        remaining_times = [
            max(0.0, key.flush_interval_seconds - (now - batch[0].queued_at))
            for key, batch in self._batches.items()
            if batch
        ]
        if not remaining_times:
            return self.flush_interval_seconds
        return max(0.001, min(self.flush_interval_seconds, min(remaining_times)))

    async def _flush_all(self) -> None:
        for key in list(self._batches):
            await self._flush_batch(key)

    async def _flush_batch(self, key: _PostBatchKey) -> None:
        batch = self._batches.pop(key, None)
        if not batch:
            return
        envelope = _PostEnvelope(key=key, items=batch, queued_at=batch[0].queued_at)
        await self._send_queue.put(envelope)

    async def _sender_loop(self, worker_id: int) -> None:
        logger.debug("HTTP sender worker %d started", worker_id)
        while True:
            envelope = await self._send_queue.get()
            try:
                if envelope is _STOP:
                    return
                assert isinstance(envelope, _PostEnvelope)
                await self._run_with_retry(
                    lambda env=envelope: self._send_envelope(env),
                    retry_attempts=envelope.key.retry_attempts,
                    backoff_seconds=envelope.key.backoff_seconds,
                )
            except (httpx.ConnectTimeout, httpx.PoolTimeout):
                logger.warning(
                    "POST timeout | source=%s url=%s batch_size=%d",
                    envelope.key.source,
                    envelope.key.url,
                    len(envelope.items) if isinstance(envelope, _PostEnvelope) else 0,
                )
            except Exception:
                logger.exception(
                    "POST failed | source=%s url=%s",
                    envelope.key.source if isinstance(envelope, _PostEnvelope) else "?",
                    envelope.key.url if isinstance(envelope, _PostEnvelope) else "?",
                )
            finally:
                self._send_queue.task_done()

    async def _send_envelope(self, envelope: _PostEnvelope) -> None:
        if self._client is None:
            raise RuntimeError("HttpDispatcher not started — call start() first")
        if not envelope.items:
            return

        allow_batch = all(item.allow_batches for item in envelope.items)
        queued_for = max(0.0, time.monotonic() - envelope.queued_at)

        if allow_batch:
            payload: Any = [item.body for item in envelope.items]
            await self._post_once(
                url=envelope.key.url,
                headers=envelope.items[0].headers or {},
                payload=payload,
                log_ctx={
                    "source": envelope.key.source,
                    "url": envelope.key.url,
                    "batch_size": len(envelope.items),
                    "queued_for_seconds": round(queued_for, 4),
                },
            )
        else:
            for item in envelope.items:
                await self._post_once(
                    url=envelope.key.url,
                    headers=item.headers or {},
                    payload=item.body,
                    log_ctx={
                        "source": envelope.key.source,
                        "url": envelope.key.url,
                        "batch_size": 1,
                        "queued_for_seconds": round(queued_for, 4),
                    },
                )

    async def _post_once(
        self,
        url: str,
        headers: dict[str, Any],
        payload: Any,
        log_ctx: dict[str, Any],
    ) -> None:
        norm_headers: dict[str, str] = {str(k): str(v) for k, v in headers.items()}
        norm_headers.setdefault("Content-Type", "application/json")
        body_bytes = orjson.dumps(payload)
        start = time.monotonic()

        try:
            response = await self._client.post(url, headers=norm_headers, content=body_bytes)  # type: ignore[union-attr]
            response.raise_for_status()
            logger.info(
                "POST dispatched | %s",
                json.dumps(
                    {
                        **log_ctx,
                        "status": response.status_code,
                        "latency_seconds": round(time.monotonic() - start, 4),
                        "response_preview": response.text[:300],
                    }
                ),
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "POST HTTP error | %s",
                json.dumps(
                    {
                        **log_ctx,
                        "status": exc.response.status_code,
                        "latency_seconds": round(time.monotonic() - start, 4),
                        "response": exc.response.text[:300],
                    }
                ),
            )
            raise
        except httpx.TimeoutException:
            logger.error(
                "POST timeout | %s",
                json.dumps({**log_ctx, "latency_seconds": round(time.monotonic() - start, 4)}),
            )
            raise
        except Exception as exc:
            logger.error(
                "POST failed | %s",
                json.dumps(
                    {
                        **log_ctx,
                        "error": str(exc),
                        "latency_seconds": round(time.monotonic() - start, 4),
                    }
                ),
            )
            raise

    @staticmethod
    async def _run_with_retry(operation: Any, retry_attempts: int, backoff_seconds: float) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            try:
                await operation()
                return
            except Exception as exc:
                last_exc = exc
                if attempt >= retry_attempts:
                    break
                await asyncio.sleep(max(0.0, backoff_seconds) * attempt)
        if last_exc is not None:
            raise last_exc


__all__ = ["HttpDispatcher", "_PostItem"]
