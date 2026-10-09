import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


_STOP = object()


@dataclass(slots=True, frozen=True)
class _MongoBatchKey:
    source: str
    connection_string: str
    database: str
    collection: str
    ordered: bool
    batch_size: int
    allow_batches: bool
    flush_interval_seconds: float
    retry_attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class _MongoItem:
    key: _MongoBatchKey
    document: Any
    queued_at: float


@dataclass(slots=True)
class _MongoEnvelope:
    key: _MongoBatchKey
    items: list[_MongoItem]
    queued_at: float


class MongoDispatcher:
    """
    Manages all MongoDB dispatch operations.
    Batching is opt-in per dispatch (``allow_batches`` field in JSON config).

    Parameters
    ----------
    batch_size : int
            Max documents per batch insert (default 1000).
    flush_interval_seconds : float
            How often to flush pending batches (default 0.1).
    sender_workers : int
            Concurrent sender coroutines (default 32).
    queue_max_size : int
            Max items in internal queues (default 10_000).
    """

    def __init__(
        self,
        batch_size: int = 1000,
        flush_interval_seconds: float = 0.1,
        sender_workers: int = 32,
        queue_max_size: int = 10_000,
    ) -> None:
        self.batch_size = max(1, batch_size)
        self.flush_interval_seconds = max(0.001, flush_interval_seconds)
        self.sender_workers = max(1, sender_workers)
        self.queue_max_size = max(1, queue_max_size)

        self._batch_queue: asyncio.Queue[_MongoItem | object] = asyncio.Queue(maxsize=self.queue_max_size)
        self._send_queue: asyncio.Queue[_MongoEnvelope | object] = asyncio.Queue(maxsize=self.queue_max_size)
        self._batches: dict[_MongoBatchKey, list[_MongoItem]] = {}
        self._clients: dict[str, Any] = {}
        self._batch_task: asyncio.Task | None = None
        self._worker_tasks: list[asyncio.Task] = []

    def start(self) -> None:
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._batch_loop(), name="mongo-dispatcher-batcher")
        if not self._worker_tasks:
            self._worker_tasks = [
                asyncio.create_task(self._sender_loop(i + 1), name=f"mongo-dispatcher-sender-{i + 1}")
                for i in range(self.sender_workers)
            ]
        logger.debug(
            "MongoDispatcher started | batch_size=%d flush_interval=%.3fs sender_workers=%d",
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

        await self._close_all_clients()
        logger.debug("MongoDispatcher stopped")

    async def flush(self) -> None:
        await self._batch_queue.join()
        await self._flush_all()
        await self._send_queue.join()

    async def enqueue(self, item: _MongoItem) -> None:
        try:
            self._batch_queue.put_nowait(item)
        except asyncio.QueueFull:
            await asyncio.wait_for(self._batch_queue.put(item), timeout=0.2)

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

            assert isinstance(item, _MongoItem)
            batch = self._batches.setdefault(item.key, [])
            batch.append(item)
            self._batch_queue.task_done()

            if not item.key.allow_batches or len(batch) >= item.key.batch_size:
                await self._flush_batch(item.key)
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

    async def _flush_batch(self, key: _MongoBatchKey) -> None:
        batch = self._batches.pop(key, None)
        if not batch:
            return
        envelope = _MongoEnvelope(key=key, items=batch, queued_at=batch[0].queued_at)
        await self._send_queue.put(envelope)

    async def _sender_loop(self, worker_id: int) -> None:
        logger.debug("Mongo sender worker %d started", worker_id)
        while True:
            envelope = await self._send_queue.get()
            try:
                if envelope is _STOP:
                    return
                assert isinstance(envelope, _MongoEnvelope)
                await self._run_with_retry(
                    lambda env=envelope: self._send_envelope(env),
                    retry_attempts=envelope.key.retry_attempts,
                    backoff_seconds=envelope.key.backoff_seconds,
                )
            except TimeoutError:
                logger.warning(
                    "Mongo timeout | source=%s db=%s collection=%s batch_size=%d",
                    envelope.key.source if isinstance(envelope, _MongoEnvelope) else "?",
                    envelope.key.database if isinstance(envelope, _MongoEnvelope) else "?",
                    envelope.key.collection if isinstance(envelope, _MongoEnvelope) else "?",
                    len(envelope.items) if isinstance(envelope, _MongoEnvelope) else 0,
                )
            except Exception:
                logger.exception(
                    "Mongo failed | source=%s db=%s collection=%s",
                    envelope.key.source if isinstance(envelope, _MongoEnvelope) else "?",
                    envelope.key.database if isinstance(envelope, _MongoEnvelope) else "?",
                    envelope.key.collection if isinstance(envelope, _MongoEnvelope) else "?",
                )
            finally:
                self._send_queue.task_done()

    async def _send_envelope(self, envelope: _MongoEnvelope) -> None:
        if not envelope.items:
            return

        allow_batch = all(item.key.allow_batches for item in envelope.items)
        queued_for = max(0.0, time.monotonic() - envelope.queued_at)

        if allow_batch:
            docs = [self._as_document(item.document) for item in envelope.items]
            await self._insert_many_once(
                key=envelope.key,
                docs=docs,
                log_ctx={
                    "source": envelope.key.source,
                    "database": envelope.key.database,
                    "collection": envelope.key.collection,
                    "batch_size": len(docs),
                    "queued_for_seconds": round(queued_for, 4),
                },
            )
        else:
            for item in envelope.items:
                await self._insert_many_once(
                    key=envelope.key,
                    docs=[self._as_document(item.document)],
                    log_ctx={
                        "source": envelope.key.source,
                        "database": envelope.key.database,
                        "collection": envelope.key.collection,
                        "batch_size": 1,
                        "queued_for_seconds": round(queued_for, 4),
                    },
                )

    async def _insert_many_once(self, key: _MongoBatchKey, docs: list[dict[str, Any]], log_ctx: dict[str, Any]) -> None:
        if not docs:
            return

        client = self._clients.get(key.connection_string)
        if client is None:
            client = self._create_client(key.connection_string)
            self._clients[key.connection_string] = client

        start = time.monotonic()
        try:
            collection = client[key.database][key.collection]
            result = await collection.insert_many(docs, ordered=key.ordered)
            logger.info(
                "Mongo dispatched | %s",
                json.dumps(
                    {
                        **log_ctx,
                        "inserted_count": len(result.inserted_ids),
                        "latency_seconds": round(time.monotonic() - start, 4),
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Mongo failed | %s",
                json.dumps(
                    {
                        **log_ctx,
                        "error": str(exc),
                        "latency_seconds": round(time.monotonic() - start, 4),
                    }
                ),
            )
            raise

    def _create_client(self, connection_string: str) -> Any:
        try:
            from pymongo import AsyncMongoClient  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("MongoDB dispatch requires 'pymongo'. Install with: poetry add pymongo") from exc
        return AsyncMongoClient(connection_string)

    async def _close_all_clients(self) -> None:
        for client in self._clients.values():
            try:
                maybe = client.close()
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception:
                logger.debug("Error while closing MongoDB client", exc_info=True)
        self._clients.clear()

    @staticmethod
    def _as_document(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {"value": value}

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


__all__ = ["MongoDispatcher", "_MongoBatchKey", "_MongoItem"]
