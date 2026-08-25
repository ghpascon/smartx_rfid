"""
event_dispatcher.py
-------------------
Async event dispatcher that routes named events to HTTP POST or SQL destinations
based on JSON configuration files stored on disk.

Usage
-----
    dispatcher = EventDispatcher(dispatches_path="dispatches/")
    await dispatcher.start()
    await dispatcher.add_async("my_service", "user.created", {"id": 1})
    await dispatcher.stop()

Dispatch JSON schema
--------------------
POST:
    {
        "dispatch_type": "post",
        "on_event": "user.created",
        "url": "https://example.com/hook",
        "headers": {"X-Token": "abc"},
        "body": {"id": "{data[id]}"},
        "allow_batches": true,
        "batch_size": 500,
        "flush_interval_seconds": 0.1,
        "retry_attempts": 3,
        "retry_backoff_seconds": 0.25,
        "filters": [{"key": "{data[status]}", "value": "active", "operator": "eq"}]
    }

SQL:
    {
        "dispatch_type": "sql",
        "on_event": "user.created",
        "connection_string": "postgresql://user:pass@host/db",
        "query": "INSERT INTO events (name, type) VALUES (:name, :event_type)",
        "params": {"name": "{name}", "event_type": "{event_type}"},
        "allow_batches": true,
        "batch_size": 500,
        "flush_interval_seconds": 0.1,
        "retry_attempts": 3,
        "retry_backoff_seconds": 0.25
    }

Template placeholders: {name}, {event_type}, {data}, {data[key]}
"""

# noqa: E741

import asyncio
import atexit
import copy
import json
import logging
import re
import signal
import time
import weakref
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import httpx
import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
import oracledb


logger = logging.getLogger(__name__)


try:
    oracledb.init_oracle_client()
    logger.info("Oracle client initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize Oracle client: {e}")

# ---------------------------------------------------------------------------
# Sentinels and patterns
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")
_DATA_KEY_PATTERN = re.compile(r"^data\[([^\]]+)\]$")
_STOP = object()


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Event:
    event_id: int
    name: str
    event_type: str
    data: Any
    queued_at: float


@dataclass(slots=True, frozen=True)
class _SqlBatchKey:
    connection_string: str
    query: str
    batch_size: int
    allow_batches: bool
    flush_interval_seconds: float
    retry_attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class _SqlItem:
    key: _SqlBatchKey
    params: dict[str, Any]
    queued_at: float


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


@dataclass(slots=True, frozen=True)
class _CompiledFilter:
    key_fn: Callable[[dict[str, Any]], Any]
    value_fn: Callable[[dict[str, Any]], Any]
    operator: str


@dataclass(slots=True)
class _CompiledDispatch:
    source: str
    dispatch_type: str
    batch_size: int
    allow_batches: bool
    flush_interval_seconds: float
    event_type_fn: Callable[[dict[str, Any]], Any]
    event_type_static: str | None
    filters: tuple[_CompiledFilter, ...]
    retry_attempts: int
    backoff_seconds: float
    url_fn: Callable[[dict[str, Any]], Any] | None
    headers_fn: Callable[[dict[str, Any]], Any] | None
    body_fn: Callable[[dict[str, Any]], Any] | None
    connection_fn: Callable[[dict[str, Any]], Any] | None
    query_fn: Callable[[dict[str, Any]], Any] | None
    params_fn: Callable[[dict[str, Any]], Any] | None
    sql_key_static: _SqlBatchKey | None


@dataclass
class _RouteBucket:
    post: list[_CompiledDispatch] = field(default_factory=list)
    sql: list[_CompiledDispatch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SqlDispatcher — always batched
# ---------------------------------------------------------------------------


class SqlDispatcher:
    """
    Manages all SQL dispatch operations using mandatory batching.

    Parameters
    ----------
    batch_size : int
        Maximum number of rows flushed per execution (default 1000).
    flush_interval_seconds : float
        How often to flush pending batches when not full (default 0.1).
    queue_max_size : int
        Max items in the internal queue before back-pressure (default 10_000).
    """

    def __init__(
        self,
        batch_size: int = 1000,
        flush_interval_seconds: float = 0.1,
        queue_max_size: int = 10_000,
    ) -> None:
        self.batch_size = max(1, batch_size)
        self.flush_interval_seconds = max(0.001, flush_interval_seconds)
        self.queue_max_size = max(1, queue_max_size)

        self._queue: asyncio.Queue[_SqlItem | object] = asyncio.Queue(maxsize=self.queue_max_size)
        self._batches: dict[_SqlBatchKey, list[_SqlItem]] = {}
        self._engines: dict[str, AsyncEngine] = {}
        self._stmt_cache: dict[str, Any] = {}
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="sql-dispatcher-batcher")
            logger.debug(
                "SqlDispatcher started | batch_size=%d flush_interval=%.3fs",
                self.batch_size,
                self.flush_interval_seconds,
            )

    async def stop(self, drain: bool = True) -> None:
        if self._task is None:
            return
        if drain:
            await self._queue.join()
            await self._flush_all()
        await self._queue.put(_STOP)
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        logger.debug("SqlDispatcher stopped")

    async def flush(self) -> None:
        await self._queue.join()
        await self._flush_all()

    # ------------------------------------------------------------------
    # Engine management (called by EventDispatcher.reload_dispatches)
    # ------------------------------------------------------------------

    def ensure_engine(self, connection_string: str) -> None:
        if connection_string not in self._engines:
            self._create_engine(connection_string)
            logger.debug("SQL engine created: %s", connection_string)

    def remove_stale_engines(self, active_connections: set[str]) -> None:
        for key in set(self._engines) - active_connections:
            try:
                engine = self._engines.pop(key)
                asyncio.create_task(engine.dispose())
                logger.debug("SQL engine disposed: %s", key)
            except Exception:
                logger.debug("Error disposing SQL engine: %s", key, exc_info=True)

    async def dispose_all(self) -> None:
        for engine in self._engines.values():
            try:
                await engine.dispose()
            except Exception:
                logger.debug("Error disposing SQL engine during shutdown", exc_info=True)
        self._engines.clear()

    def clear_stmt_cache(self) -> None:
        self._stmt_cache.clear()

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def enqueue(self, item: _SqlItem, add_timeout: float = 0.2) -> None:
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            if add_timeout <= 0:
                raise
            await asyncio.wait_for(self._queue.put(item), timeout=add_timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self._next_timeout())
            except TimeoutError:
                await self._flush_due()
                continue

            if item is _STOP:
                self._queue.task_done()
                await self._flush_all()
                return

            assert isinstance(item, _SqlItem)
            batch = self._batches.setdefault(item.key, [])
            batch.append(item)
            if not item.key.allow_batches or len(batch) >= item.key.batch_size:
                await self._flush(item.key)
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
                await self._flush(key)

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
            await self._flush(key)

    async def _flush(self, key: _SqlBatchKey) -> None:
        batch = self._batches.pop(key, None)
        if not batch:
            return

        params_list = [item.params for item in batch]
        start = time.monotonic()

        try:
            await self._run_with_retry(
                lambda: self._execute_many(key.connection_string, key.query, params_list),
                retry_attempts=key.retry_attempts,
                backoff_seconds=key.backoff_seconds,
            )
            logger.info(
                "SQL batch dispatched | query=%r rows=%d sample_params=%s latency=%.4fs",
                key.query,
                len(params_list),
                params_list[0] if params_list else {},
                time.monotonic() - start,
            )
        except Exception:
            logger.exception(
                "SQL batch failed | query=%r rows=%d sample_params=%s latency=%.4fs",
                key.query,
                len(params_list),
                params_list[0] if params_list else {},
                time.monotonic() - start,
            )
        finally:
            for _ in batch:
                self._queue.task_done()

    async def _execute_many(self, connection_string: str, query: str, params_list: list[dict[str, Any]]) -> None:
        engine = self._engines.get(connection_string) or self._create_engine(connection_string)
        stmt = self._stmt_cache.get(query)
        if stmt is None:
            stmt = text(query)
            self._stmt_cache[query] = stmt
        async with engine.connect() as conn:
            await conn.execute(stmt, params_list)
            await conn.commit()

    def _create_engine(self, connection_string: str):
        kwargs = {
            "pool_pre_ping": True,
        }

        # detecta sqlite
        is_sqlite = connection_string.startswith("sqlite")

        if not is_sqlite:
            kwargs.update(
                {
                    "pool_size": 20,
                    "max_overflow": 30,
                    "pool_recycle": 1800,
                    "future": True,
                }
            )

        engine = create_async_engine(connection_string, **kwargs)

        self._engines[connection_string] = engine
        return engine

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


# ---------------------------------------------------------------------------
# HttpDispatcher — optional batching per dispatch config
# ---------------------------------------------------------------------------


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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def enqueue(self, item: _PostItem) -> None:
        try:
            self._batch_queue.put_nowait(item)
        except asyncio.QueueFull:
            await asyncio.wait_for(self._batch_queue.put(item), timeout=0.2)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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

            # flush immediately if batching disabled for this item or batch is full
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
            # Sempre envia como lista se allow_batches for True, mesmo que só tenha um item
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
            # send each body individually — never wrapped in a list
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


# ---------------------------------------------------------------------------
# EventDispatcher — main coordinator
# ---------------------------------------------------------------------------


class EventDispatcher:
    """
    Async event dispatcher. Routes events to HTTP POST or SQL targets based on
    JSON dispatch config files loaded from ``dispatches_path``.

    Auto-starts on the first call to ``add`` or ``add_async`` if not started
    manually. Gracefully drains all queues on ``stop(drain=True)`` and on
    process exit (atexit / SIGINT / SIGTERM).

    Parameters
    ----------
    dispatches_path : str
        Directory containing ``*.json`` dispatch config files.
    example_path : str | None
        Optional directory for example event ``*.json`` files.
    max_workers : int
        Concurrent event-processing workers (default 10).
    max_queue_size : int
        Max events in the internal queue before back-pressure (default 10_000).
    sql : SqlDispatcher | None
        Optional pre-configured SqlDispatcher. Creates a default one if omitted.
    http : HttpDispatcher | None
        Optional pre-configured HttpDispatcher. Creates a default one if omitted.

    Custom tuning example
    ---------------------
        dispatcher = EventDispatcher(
            dispatches_path="dispatches/",
            sql=SqlDispatcher(batch_size=200, flush_interval_seconds=0.1),
            http=HttpDispatcher(batch_size=100, sender_workers=32),
        )
    """

    def __init__(
        self,
        dispatches_path: str,
        example_path: str | None = None,
        max_workers: int = 10,
        max_queue_size: int = 10_000,
        sql: "SqlDispatcher | None" = None,
        http: "HttpDispatcher | None" = None,
    ) -> None:
        self.dispatches_path = dispatches_path
        self.example_path = example_path
        self.max_workers = max(1, max_workers)
        self.max_queue_size = max(1, max_queue_size)

        Path(dispatches_path).mkdir(parents=True, exist_ok=True)
        if example_path:
            Path(example_path).mkdir(parents=True, exist_ok=True)

        self._sql = sql or SqlDispatcher()
        self._http = http or HttpDispatcher()

        self._event_queue: asyncio.Queue[_Event | object] = asyncio.Queue(maxsize=self.max_queue_size)
        self._workers: list[asyncio.Task] = []
        self._inflight: dict[int, _Event] = {}

        self._started = False
        self._shutdown_started = False
        self._start_lock = asyncio.Lock()
        self._start_task: asyncio.Task | None = None

        # Routing tables
        self._dispatches: list[dict[str, Any]] = []
        self._compiled: list[_CompiledDispatch] = []
        self._routes_by_event: dict[str, _RouteBucket] = {}
        self._routes_any = _RouteBucket()

        # Dedup ring-buffer (prevents duplicate processing on restart/fallback)
        self._next_event_id = 1
        self._processed_ids: set[int] = set()
        self._processed_order: deque[int] = deque()
        self._processed_limit = 100_000

        # Stats
        self._stats: dict[str, int] = {
            "events_received": 0,
            "events_queued": 0,
            "events_dropped": 0,
            "events_processed": 0,
            "dispatches_attempted": 0,
            "dispatches_succeeded": 0,
            "dispatches_failed": 0,
        }

        weakref.finalize(self, self._sync_shutdown, "finalizer")
        atexit.register(self._sync_shutdown, "atexit")
        self._register_signals()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            self.reload_dispatches()
            self._http.start()
            self._sql.start()
            self._workers = [
                asyncio.create_task(self._worker_loop(i + 1), name=f"event-dispatcher-worker-{i + 1}")
                for i in range(self.max_workers)
            ]
            self._started = True
            logger.info(
                "EventDispatcher started | workers=%d queue_size=%d dispatches=%d",
                self.max_workers,
                self.max_queue_size,
                len(self._compiled),
            )

    async def stop(self, drain: bool = True) -> None:
        if not self._started:
            return
        if drain:
            await self.flush()

        # Signal workers to stop
        for _ in self._workers:
            await self._event_queue.put(_STOP)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        # Stop sub-dispatchers (they drain internally if drain=True)
        await self._http.stop(drain=drain)
        await self._sql.stop(drain=drain)
        await self._sql.dispose_all()

        self._started = False
        self._start_task = None
        logger.info("EventDispatcher stopped")

    async def flush(self, timeout: float | None = None) -> None:
        """Wait for all queued events and pending dispatches to complete."""

        async def _flush_all() -> None:
            await self._event_queue.join()
            await self._http.flush()
            await self._sql.flush()

        if timeout is None:
            await _flush_all()
        else:
            await asyncio.wait_for(_flush_all(), timeout=timeout)

    # ------------------------------------------------------------------
    # Public API — add events
    # ------------------------------------------------------------------

    async def add_async(self, name: str, event_type: str, data: Any = None) -> bool:
        """
        Enqueue an event. Starts the dispatcher automatically if not running.
        Returns True if accepted, False if dropped.
        """
        self._stats["events_received"] += 1
        if not self._started:
            self._ensure_start_task()
            await self.start()

        event = _Event(
            event_id=self._next_event_id,
            name=name,
            event_type=event_type,
            data=data,
            queued_at=time.monotonic(),
        )
        self._next_event_id += 1

        try:
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                await asyncio.wait_for(self._event_queue.put(event), timeout=0.2)
            self._stats["events_queued"] += 1
            logger.info("Event enqueued | name=%s event_type=%s data=%s", name, event_type, data)
            return True
        except (asyncio.QueueFull, TimeoutError):
            self._stats["events_dropped"] += 1
            logger.warning("Event dropped (queue full) | name=%s event_type=%s", name, event_type)
            return False
        except Exception:
            self._stats["events_dropped"] += 1
            logger.exception("Event dropped (error) | name=%s event_type=%s", name, event_type)
            return False

    def add(self, name: str, event_type: str, data: Any = None) -> bool:
        """
        Fire-and-forget enqueue from within a running event loop.
        Use ``add_async`` when you need confirmation the event was accepted.
        Returns True if accepted, False if dropped.
        """
        self._stats["events_received"] += 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._stats["events_dropped"] += 1
            logger.error(
                "add() requires a running event loop — use add_async() instead. Dropped: %s/%s",
                name,
                event_type,
            )
            return False

        if not self._started:
            self._ensure_start_task()

        event = _Event(
            event_id=self._next_event_id,
            name=name,
            event_type=event_type,
            data=data,
            queued_at=time.monotonic(),
        )
        self._next_event_id += 1

        try:
            self._event_queue.put_nowait(event)
            self._stats["events_queued"] += 1
            return True
        except asyncio.QueueFull:
            self._stats["events_dropped"] += 1
            logger.warning("Event dropped (queue full) | name=%s event_type=%s", name, event_type)
            return False
        except Exception:
            self._stats["events_dropped"] += 1
            logger.exception("Event dropped (error) | name=%s event_type=%s", name, event_type)
            return False

    # ------------------------------------------------------------------
    # Public API — stats and introspection
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = dict(self._stats)
        stats["queue_size"] = self._event_queue.qsize()
        stats["workers_configured"] = self.max_workers
        stats["workers_running"] = len(self._workers)
        stats["dispatches_loaded"] = len(self._compiled)
        stats["sql_batch_size"] = self._sql.batch_size
        stats["http_batch_size"] = self._http.batch_size
        stats["http_sender_workers"] = self._http.sender_workers
        return stats

    # ------------------------------------------------------------------
    # Public API — dispatch file management
    # ------------------------------------------------------------------

    def get_dispatch_names(self) -> list[str]:
        """Return sorted list of loaded dispatch names (without .json extension)."""
        try:
            return sorted(p.stem for p in Path(self.dispatches_path).glob("*.json"))
        except Exception:
            logger.exception("Failed to list dispatch files")
            return []

    def get_dispatch_content(self, name: str) -> dict | None:
        """Return the raw JSON content of a dispatch file, or None if not found."""
        try:
            path = self._dispatch_path(name)
            with open(path, encoding="utf-8") as f:
                content = json.load(f)
            return content if isinstance(content, dict) else None
        except FileNotFoundError:
            logger.warning("Dispatch not found: %s", name)
            return None
        except Exception:
            logger.exception("Failed to read dispatch: %s", name)
            return None

    def create_dispatch(
        self,
        name: str,
        content: dict[str, Any],
        *,
        overwrite: bool = False,
        validate: bool = True,
    ) -> bool:
        """
        Create a new dispatch JSON file and reload routing.
        Returns True on success, False if the file already exists and overwrite=False.
        """
        try:
            if validate:
                self._validate(content)
            path = self._dispatch_path(name)
            if path.exists() and not overwrite:
                logger.warning("Dispatch already exists (overwrite=False): %s", name)
                return False
            self._write(path, content)
            self.reload_dispatches()
            logger.info("Dispatch created: %s", name)
            return True
        except Exception:
            logger.exception("Failed to create dispatch: %s", name)
            return False

    def edit_dispatch(
        self,
        name: str,
        content: dict[str, Any],
        *,
        merge: bool = True,
        validate: bool = True,
    ) -> bool:
        """
        Edit an existing dispatch JSON file and reload routing.
        When merge=True, deeply merges content into the existing file.
        """
        try:
            path = self._dispatch_path(name)
            if not path.exists():
                logger.warning("Dispatch not found for edit: %s", name)
                return False
            with open(path, encoding="utf-8") as f:
                current = json.load(f)
            if not isinstance(current, dict):
                logger.error("Dispatch root must be a JSON object: %s", name)
                return False
            updated = self._deep_merge(current, content) if merge else copy.deepcopy(content)
            if validate:
                self._validate(updated)
            self._write(path, updated)
            self.reload_dispatches()
            logger.info("Dispatch edited: %s", name)
            return True
        except Exception:
            logger.exception("Failed to edit dispatch: %s", name)
            return False

    def delete_dispatch(self, name: str, *, missing_ok: bool = True) -> bool:
        """Delete a dispatch JSON file and reload routing."""
        try:
            path = self._dispatch_path(name)
            if not path.exists():
                if missing_ok:
                    logger.info("Dispatch already absent: %s", name)
                    return True
                logger.warning("Dispatch not found for delete: %s", name)
                return False
            path.unlink()
            self.reload_dispatches()
            logger.info("Dispatch deleted: %s", name)
            return True
        except Exception:
            logger.exception("Failed to delete dispatch: %s", name)
            return False

    # ------------------------------------------------------------------
    # Public API — example file helpers
    # ------------------------------------------------------------------

    def get_example_names(self) -> list[str]:
        """Return sorted list of example file names (without .json extension)."""
        if not self.example_path:
            return []
        try:
            return sorted(p.stem for p in Path(self.example_path).glob("*.json"))
        except Exception:
            logger.exception("Failed to list example files")
            return []

    def get_example_content(self, name: str) -> dict | None:
        """Return the raw JSON content of an example file, or None if not found."""
        if not self.example_path:
            return None
        try:
            path = Path(self.example_path) / f"{name}.json"
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Example not found: %s", name)
            return None
        except Exception:
            logger.exception("Failed to read example: %s", name)
            return None

    # ------------------------------------------------------------------
    # Dispatch reload
    # ------------------------------------------------------------------

    def reload_dispatches(self) -> None:
        """Rescan dispatches_path, recompile all dispatch plans, and rebuild routing."""
        dispatches: list[dict[str, Any]] = []
        compiled: list[_CompiledDispatch] = []
        routes_by_event: dict[str, _RouteBucket] = {}
        routes_any = _RouteBucket()
        sql_connections: set[str] = set()

        for path in Path(self.dispatches_path).glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    content = json.load(f)
                if not isinstance(content, dict):
                    logger.warning("Skipping %s — root is not a JSON object", path.name)
                    continue
                dispatches.append(content)
                plan = self._compile(content, source=path.name)
                if plan is None:
                    continue
                compiled.append(plan)
                if plan.dispatch_type == "sql" and plan.sql_key_static:
                    sql_connections.add(plan.sql_key_static.connection_string)
                bucket = (
                    routes_by_event.setdefault(plan.event_type_static, _RouteBucket())
                    if plan.event_type_static
                    else routes_any
                )
                (bucket.sql if plan.dispatch_type == "sql" else bucket.post).append(plan)
            except Exception:
                logger.exception("Failed to parse dispatch file: %s", path.name)

        self._sql.remove_stale_engines(sql_connections)
        for cs in sql_connections:
            self._sql.ensure_engine(cs)
        self._sql.clear_stmt_cache()

        self._dispatches = dispatches
        self._compiled = compiled
        self._routes_by_event = routes_by_event
        self._routes_any = routes_any

        post_count = sum(len(b.post) for b in routes_by_event.values()) + len(routes_any.post)
        sql_count = sum(len(b.sql) for b in routes_by_event.values()) + len(routes_any.sql)
        logger.info(
            "Dispatches reloaded | files=%d post_routes=%d sql_routes=%d sql_pools=%d",
            len(compiled),
            post_count,
            sql_count,
            len(sql_connections),
        )

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    async def _worker_loop(self, worker_id: int) -> None:
        logger.debug("Worker %d started", worker_id)
        while True:
            item = await self._event_queue.get()
            try:
                if item is _STOP:
                    return
                assert isinstance(item, _Event)
                self._inflight[item.event_id] = item
                if not self._was_processed(item.event_id):
                    await self._process(item)
                    self._mark_processed(item.event_id)
            except Exception:
                logger.exception("Worker %d: unhandled error", worker_id)
            finally:
                self._inflight.pop(item.event_id if isinstance(item, _Event) else -1, None)
                self._event_queue.task_done()

    async def _process(self, event: _Event) -> None:
        self._stats["events_processed"] += 1
        ctx: dict[str, Any] = {"name": event.name, "event_type": event.event_type, "data": event.data}

        bucket = self._routes_by_event.get(event.event_type)
        for plan in bucket.post if bucket else []:
            await self._dispatch_one(plan, ctx)
        for plan in bucket.sql if bucket else []:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.post:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.sql:
            await self._dispatch_one(plan, ctx)

    async def _dispatch_one(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        try:
            if not self._matches(plan, ctx):
                return
            self._stats["dispatches_attempted"] += 1
            if plan.dispatch_type == "post":
                await self._enqueue_post(plan, ctx)
            else:
                await self._enqueue_sql(plan, ctx)
            self._stats["dispatches_succeeded"] += 1
        except Exception:
            self._stats["dispatches_failed"] += 1
            logger.exception("Dispatch failed | source=%s type=%s", plan.source, plan.dispatch_type)

    async def _enqueue_post(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        item = _PostItem(
            source=plan.source,
            batch_size=plan.batch_size,
            allow_batches=plan.allow_batches,
            retry_attempts=plan.retry_attempts,
            backoff_seconds=plan.backoff_seconds,
            flush_interval_seconds=plan.flush_interval_seconds,
            url=plan.url_fn(ctx) if plan.url_fn else "",
            headers=plan.headers_fn(ctx) if plan.headers_fn else {},
            body=plan.body_fn(ctx) if plan.body_fn else {},
            queued_at=time.monotonic(),
        )
        await self._http.enqueue(item)

    async def _enqueue_sql(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        params = plan.params_fn(ctx) if plan.params_fn else {}
        if plan.sql_key_static:
            key = plan.sql_key_static
        else:
            cs = plan.connection_fn(ctx) if plan.connection_fn else ""
            q = plan.query_fn(ctx) if plan.query_fn else ""
            if not isinstance(cs, str) or not cs.strip():
                raise ValueError("SQL dispatch requires connection_string")
            if not isinstance(q, str) or not q.strip():
                raise ValueError("SQL dispatch requires query")
            key = _SqlBatchKey(
                connection_string=self._normalize_connection(cs),
                query=q,
                batch_size=plan.batch_size,
                allow_batches=plan.allow_batches,
                flush_interval_seconds=plan.flush_interval_seconds,
                retry_attempts=plan.retry_attempts,
                backoff_seconds=plan.backoff_seconds,
            )
        await self._sql.enqueue(_SqlItem(key=key, params=params, queued_at=time.monotonic()))

    # ------------------------------------------------------------------
    # Dispatch compilation
    # ------------------------------------------------------------------

    def _compile(self, content: dict[str, Any], source: str) -> _CompiledDispatch | None:
        try:
            self._validate(content)
        except ValueError as exc:
            logger.warning("Invalid dispatch %s: %s", source, exc)
            return None

        dtype = str(content.get("dispatch_type", "")).lower()
        default_batch_size = self._http.batch_size if dtype == "post" else self._sql.batch_size
        default_flush = self._http.flush_interval_seconds if dtype == "post" else self._sql.flush_interval_seconds

        allow_batches = self._coerce_bool(content.get("allow_batches"), default=True)
        batch_size = self._coerce_positive_int(content.get("batch_size"), default=default_batch_size)
        retry = self._coerce_positive_int(content.get("retry_attempts"), default=3)
        backoff = self._coerce_non_negative_float(content.get("retry_backoff_seconds"), default=0.25)
        dispatch_flush = self._coerce_positive_float(content.get("flush_interval_seconds"), default=default_flush)

        event_fn, is_static, static_val = self._build_renderer(content.get("on_event"))
        event_static = static_val if (is_static and isinstance(static_val, str) and static_val) else None

        filters = tuple(
            _CompiledFilter(
                key_fn=self._build_renderer(f.get("key"))[0],
                value_fn=self._build_renderer(f.get("value"))[0],
                operator=str(f.get("operator", "eq")).lower(),
            )
            for f in content.get("filters", [])
            if isinstance(f, dict)
        )

        plan = _CompiledDispatch(
            source=source,
            dispatch_type=dtype,
            batch_size=batch_size,
            allow_batches=allow_batches,
            flush_interval_seconds=dispatch_flush,
            event_type_fn=event_fn,
            event_type_static=event_static,
            filters=filters,
            retry_attempts=retry,
            backoff_seconds=backoff,
            url_fn=None,
            headers_fn=None,
            body_fn=None,
            connection_fn=None,
            query_fn=None,
            params_fn=None,
            sql_key_static=None,
        )

        if dtype == "post":
            plan.url_fn = self._build_renderer(content.get("url"))[0]
            plan.headers_fn = self._build_renderer(content.get("headers", {}))[0]
            plan.body_fn = self._build_renderer(content.get("body", {}))[0]
            plan.allow_batches = bool(content.get("allow_batches", True))
        elif dtype == "sql":
            conn_fn, conn_static, conn_val = self._build_renderer(content.get("connection_string"))
            query_fn, query_static, query_val = self._build_renderer(content.get("query"))
            plan.connection_fn = conn_fn
            plan.query_fn = query_fn
            plan.params_fn = self._build_renderer(content.get("params", {}))[0]
            if conn_static and query_static and isinstance(conn_val, str) and isinstance(query_val, str):
                plan.sql_key_static = _SqlBatchKey(
                    connection_string=self._normalize_connection(conn_val),
                    query=query_val,
                    batch_size=batch_size,
                    allow_batches=allow_batches,
                    flush_interval_seconds=dispatch_flush,
                    retry_attempts=retry,
                    backoff_seconds=backoff,
                )
        else:
            logger.warning("Unsupported dispatch_type=%r in %s", dtype, source)
            return None

        return plan

    # ------------------------------------------------------------------
    # Template renderer
    # ------------------------------------------------------------------

    def _build_renderer(self, value: Any) -> tuple[Callable[[dict[str, Any]], Any], bool, Any]:
        if isinstance(value, dict):
            items = [(self._build_renderer(k), self._build_renderer(v)) for k, v in value.items()]
            all_static = all(ki[1] and vi[1] for ki, vi in items)
            if all_static:
                frozen = {str(ki[2]): vi[2] for ki, vi in items}
                return (lambda _c, f=frozen: copy.copy(f)), True, frozen

            def _render_dict(ctx: dict, _items: list = items) -> dict:
                return {str(kfn(ctx)): vfn(ctx) for (kfn, _, _), (vfn, _, _) in _items}

            return _render_dict, False, None

        if isinstance(value, list):
            items_r = [self._build_renderer(i) for i in value]
            if all(i[1] for i in items_r):
                frozen = [i[2] for i in items_r]
                return (lambda _c, f=frozen: f), True, frozen

            def _render_list(ctx: dict, _fns: tuple = tuple(i[0] for i in items_r)) -> list:
                return [fn(ctx) for fn in _fns]

            return _render_list, False, None

        if isinstance(value, tuple):
            items_t = [self._build_renderer(i) for i in value]
            if all(i[1] for i in items_t):
                frozen = tuple(i[2] for i in items_t)
                return (lambda _c, f=frozen: f), True, frozen

            def _render_tuple(ctx: dict, _fns: tuple = tuple(i[0] for i in items_t)) -> tuple:
                return tuple(fn(ctx) for fn in _fns)

            return _render_tuple, False, None

        if not isinstance(value, str):
            return (lambda _c, v=value: v), True, value

        is_single, parts = self._compile_template(value)
        if is_single:
            token = parts[0][1]
            return (lambda ctx, t=token: self._resolve(t, ctx)), False, None

        if len(parts) == 1 and parts[0][0] == "lit":
            literal = parts[0][1]
            return (lambda _c, literal=literal: literal), True, literal

        def _render_template(ctx: dict, _parts: tuple = parts) -> str:
            return "".join(text if kind == "lit" else (str(self._resolve(text, ctx) or "")) for kind, text in _parts)

        return _render_template, False, None

    @staticmethod
    @lru_cache(maxsize=8192)
    def _compile_template(value: str) -> tuple[bool, tuple[tuple[str, str], ...]]:
        full = _PLACEHOLDER_PATTERN.fullmatch(value)
        if full:
            return True, (("token", full.group(1).strip()),)
        parts: list[tuple[str, str]] = []
        last = 0
        for m in _PLACEHOLDER_PATTERN.finditer(value):
            if m.start() > last:
                parts.append(("lit", value[last : m.start()]))
            parts.append(("token", m.group(1).strip()))
            last = m.end()
        if last < len(value):
            parts.append(("lit", value[last:]))
        if not parts:
            parts.append(("lit", value))
        return False, tuple(parts)

    @staticmethod
    def _resolve(token: str, ctx: dict[str, Any]) -> Any:
        if token in ("name", "event_type", "data"):
            return ctx.get(token)
        m = _DATA_KEY_PATTERN.match(token)
        if m:
            data = ctx.get("data")
            return data.get(m.group(1)) if isinstance(data, dict) else None
        return None

    # ------------------------------------------------------------------
    # Filter evaluation
    # ------------------------------------------------------------------

    def _matches(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> bool:
        try:
            if plan.event_type_static is not None:
                if plan.event_type_static != ctx["event_type"]:
                    return False
            else:
                ev = plan.event_type_fn(ctx)
                if isinstance(ev, str) and ev and ev != ctx["event_type"]:
                    return False
            for f in plan.filters:
                if not self._eval_filter(f.key_fn(ctx), f.value_fn(ctx), f.operator):
                    return False
            return True
        except Exception:
            logger.exception("Filter evaluation error | source=%s", plan.source)
            return False

    @staticmethod
    def _eval_filter(key: Any, value: Any, op: str) -> bool:
        try:
            if op == "eq":
                return key == value
            if op == "ne":
                return key != value
            if op == "in":
                return key in value if isinstance(value, (list, tuple, set)) else False
            if op == "not_in":
                return key not in value if isinstance(value, (list, tuple, set)) else False
            if op == "gt":
                return key > value
            if op == "lt":
                return key < value
            if op == "gte":
                return key >= value
            if op == "lte":
                return key <= value
            if op == "contains":
                if isinstance(key, str):
                    return str(value) in key
                return value in key if isinstance(key, (list, tuple, set, dict)) else False
        except Exception:
            pass
        logger.warning("Unsupported or failed filter operator: %s", op)
        return False

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _dispatch_path(self, name: str) -> Path:
        name = name.strip()
        if not name:
            raise ValueError("Dispatch name cannot be empty")
        if any(c in name for c in ("/", "\\")):
            raise ValueError("Dispatch name must not contain path separators")
        if name in {".", ".."}:
            raise ValueError("Invalid dispatch name")
        if not name.endswith(".json"):
            name = f"{name}.json"
        base = Path(self.dispatches_path).resolve()
        path = (base / name).resolve()
        path.relative_to(base)  # raises ValueError if path escapes base
        return path

    @staticmethod
    def _write(path: Path, content: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = EventDispatcher._deep_merge(merged[k], v)
            else:
                merged[k] = copy.deepcopy(v)
        return merged

    @staticmethod
    def _validate(content: dict[str, Any]) -> None:
        if not isinstance(content, dict):
            raise ValueError("Dispatch root must be a JSON object")
        dtype = content.get("dispatch_type")
        if dtype not in ("post", "sql"):
            raise ValueError("dispatch_type must be 'post' or 'sql'")
        on_event = content.get("on_event")
        if not isinstance(on_event, str) or not on_event.strip():
            raise ValueError("on_event must be a non-empty string")
        filters = content.get("filters", [])
        if not isinstance(filters, list):
            raise ValueError("filters must be a list")
        for item in filters:
            if not isinstance(item, dict):
                raise ValueError("Each filters entry must be a JSON object")
            if "operator" in item and not isinstance(item["operator"], str):
                raise ValueError("filter operator must be a string")

        if "allow_batches" in content and not isinstance(content["allow_batches"], bool):
            raise ValueError("allow_batches must be a boolean")

        if "batch_size" in content:
            try:
                batch_size = int(content["batch_size"])
            except (TypeError, ValueError):
                raise ValueError("batch_size must be an integer") from None
            if batch_size <= 0:
                raise ValueError("batch_size must be greater than zero")

        if "flush_interval_seconds" in content:
            try:
                flush = float(content["flush_interval_seconds"])
            except (TypeError, ValueError):
                raise ValueError("flush_interval_seconds must be a number") from None
            if flush <= 0:
                raise ValueError("flush_interval_seconds must be greater than zero")

        if "retry_attempts" in content:
            try:
                retry_attempts = int(content["retry_attempts"])
            except (TypeError, ValueError):
                raise ValueError("retry_attempts must be an integer") from None
            if retry_attempts <= 0:
                raise ValueError("retry_attempts must be greater than zero")

        if "retry_backoff_seconds" in content:
            try:
                retry_backoff = float(content["retry_backoff_seconds"])
            except (TypeError, ValueError):
                raise ValueError("retry_backoff_seconds must be a number") from None
            if retry_backoff < 0:
                raise ValueError("retry_backoff_seconds must be greater than or equal to zero")
        if dtype == "post":
            url = content.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("post dispatch requires a non-empty url")
            headers = content.get("headers", {})
            if headers is not None and not isinstance(headers, dict):
                raise ValueError("headers must be a JSON object when provided")
        if dtype == "sql":
            for fname in ("connection_string", "query"):
                val = content.get(fname)
                if not isinstance(val, str) or not val.strip():
                    raise ValueError(f"sql dispatch requires non-empty {fname}")
            params = content.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("sql dispatch params must be a JSON object")

    @staticmethod
    def _coerce_positive_float(value: Any, default: float, minimum: float = 0.001) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = float(default)
        return max(minimum, parsed)

    @staticmethod
    def _coerce_non_negative_float(value: Any, default: float, minimum: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = float(default)
        return max(minimum, parsed)

    @staticmethod
    def _coerce_positive_int(value: Any, default: int, minimum: int = 1) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(minimum, parsed)

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def _normalize_connection(cs: str) -> str:
        cs = cs.strip()
        if "+" in cs.split("://", 1)[0]:
            return cs
        for prefix, async_prefix in (
            ("postgresql://", "postgresql+asyncpg://"),
            ("mysql://", "mysql+aiomysql://"),
            ("sqlite://", "sqlite+aiosqlite://"),
        ):
            if cs.startswith(prefix):
                return cs.replace(prefix, async_prefix, 1)
        return cs

    # ------------------------------------------------------------------
    # Dedup ring-buffer
    # ------------------------------------------------------------------

    def _was_processed(self, event_id: int) -> bool:
        return event_id in self._processed_ids

    def _mark_processed(self, event_id: int) -> None:
        if event_id in self._processed_ids:
            return
        self._processed_ids.add(event_id)
        self._processed_order.append(event_id)
        if len(self._processed_order) > self._processed_limit:
            self._processed_ids.discard(self._processed_order.popleft())

    # ------------------------------------------------------------------
    # Shutdown / signal helpers
    # ------------------------------------------------------------------

    def _ensure_start_task(self) -> None:
        if not self._started and (self._start_task is None or self._start_task.done()):
            self._start_task = asyncio.create_task(self.start())

    def _sync_shutdown(self, reason: str = "unknown") -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        logger.info("EventDispatcher shutdown triggered | reason=%s", reason)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.stop(drain=True))
                return
        except RuntimeError:
            pass
        try:
            asyncio.run(self.stop(drain=True))
        except Exception:
            logger.exception("Error during EventDispatcher shutdown")

    def _register_signals(self) -> None:
        try:
            prev_int = signal.getsignal(signal.SIGINT)
            prev_term = signal.getsignal(signal.SIGTERM)

            def _handler(signum: int, frame: Any) -> None:
                sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
                logger.warning("Received %s — shutting down EventDispatcher", sig_name)
                self._sync_shutdown(f"signal:{sig_name}")
                prev = prev_int if signum == signal.SIGINT else prev_term
                if callable(prev):
                    prev(signum, frame)

            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except Exception:
            logger.debug("Could not register signal handlers", exc_info=True)
