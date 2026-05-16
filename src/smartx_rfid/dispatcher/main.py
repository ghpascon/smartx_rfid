import atexit
import asyncio
import copy
import json
import logging
import re
import signal
import time
import weakref
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import httpx
import orjson
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")
_DATA_KEY_PATTERN = re.compile(r"^data\[([^\]]+)\]$")
_STOP = object()


@dataclass(slots=True)
class _DispatchEvent:
    event_id: int
    name: str
    event_type: str
    data: Any
    queued_at: float


@dataclass(slots=True, frozen=True)
class _SqlBatchKey:
    connection_string: str
    query: str
    retry_attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class _SqlDispatchItem:
    key: _SqlBatchKey
    params: dict[str, Any]
    queued_at: float


@dataclass(slots=True)
class _PostDispatchItem:
    source_name: str
    retry_attempts: int
    backoff_seconds: float
    url: str
    headers: dict[str, Any] | None
    body: Any
    queued_at: float


@dataclass(slots=True, frozen=True)
class _PostBatchKey:
    source_name: str
    url: str
    headers_json: str
    retry_attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class _PostBatchEnvelope:
    key: _PostBatchKey
    items: list[_PostDispatchItem]
    queued_at: float


@dataclass(slots=True, frozen=True)
class _CompiledFilter:
    key_renderer: Callable[[dict[str, Any]], Any]
    value_renderer: Callable[[dict[str, Any]], Any]
    operator: str


@dataclass(slots=True)
class _CompiledDispatch:
    source_name: str
    dispatch_type: str
    on_event_renderer: Callable[[dict[str, Any]], Any]
    on_event_static: str | None
    filters: tuple[_CompiledFilter, ...]
    retry_attempts: int
    backoff_seconds: float
    url_renderer: Callable[[dict[str, Any]], Any] | None
    headers_renderer: Callable[[dict[str, Any]], Any] | None
    body_renderer: Callable[[dict[str, Any]], Any] | None
    connection_renderer: Callable[[dict[str, Any]], Any] | None
    query_renderer: Callable[[dict[str, Any]], Any] | None
    params_renderer: Callable[[dict[str, Any]], Any] | None
    sql_key_static: _SqlBatchKey | None


@dataclass(slots=True)
class _DispatchRouteBucket:
    post: list[_CompiledDispatch]
    sql: list[_CompiledDispatch]


class EventDispatcher:
    def __init__(
        self,
        dispatches_path: str,
        example_path: str | None = None,
        max_workers: int = 10,
        max_queue_size: int = 10_000,
        add_timeout_seconds: float = 0.2,
        http_timeout_seconds: float = 5.0,
        default_retry_attempts: int = 1,
        default_retry_backoff_seconds: float = 0.25,
        enable_enqueue_logs: bool = True,
        enable_dispatch_success_logs: bool = True,
        success_log_first_n: int = 50,
        success_log_every_n: int = 100,
        sql_batch_enabled: bool = True,
        sql_batch_size: int = 100,
        sql_batch_flush_interval_seconds: float = 0.05,
        sql_batch_max_queue_size: int = 10_000,
        post_batch_enabled: bool = True,
        post_batch_size: int = 50,
        post_batch_flush_interval_seconds: float = 0.02,
        post_workers: int | None = None,
        post_worker_concurrency: int = 2,
        post_max_sender_workers: int = 128,
        post_queue_max_size: int = 10_000,
        post_connect_timeout_seconds: float = 2.0,
        post_pool_timeout_seconds: float = 2.0,
        post_max_http_connections: int | None = 500,
        post_max_keepalive_connections: int | None = 500,
        post_max_inflight_requests: int | None = 500,
        enable_post_success_logs: bool = True,
        suppress_httpx_request_logs: bool = True,
        http2_enabled: bool = True,
    ):
        self.dispatches_path = dispatches_path
        self.example_path = example_path
        self.max_workers = max(1, max_workers)
        self.max_queue_size = max(1, max_queue_size)
        self.add_timeout_seconds = max(0.0, add_timeout_seconds)
        self.http_timeout_seconds = max(0.1, http_timeout_seconds)
        self.default_retry_attempts = max(1, default_retry_attempts)
        self.default_retry_backoff_seconds = max(0.0, default_retry_backoff_seconds)
        self.enable_enqueue_logs = enable_enqueue_logs
        self.enable_dispatch_success_logs = enable_dispatch_success_logs
        self.enable_post_success_logs = enable_post_success_logs
        self.success_log_first_n = max(0, success_log_first_n)
        self.success_log_every_n = max(1, success_log_every_n)
        self.sql_batch_enabled = sql_batch_enabled
        self.sql_batch_size = max(1, sql_batch_size)
        self.sql_batch_flush_interval_seconds = max(0.001, sql_batch_flush_interval_seconds)
        self.sql_batch_max_queue_size = max(1, sql_batch_max_queue_size)
        self.post_batch_enabled = post_batch_enabled
        self.post_batch_size = max(1, post_batch_size)
        self.post_batch_flush_interval_seconds = max(0.001, post_batch_flush_interval_seconds)
        self.post_workers = max(1, post_workers if post_workers is not None else self.max_workers * 4)
        self.post_worker_concurrency = max(1, post_worker_concurrency)
        self.post_max_sender_workers = max(1, post_max_sender_workers)
        computed_post_workers = min(self.post_workers * self.post_worker_concurrency, self.post_max_sender_workers)
        self.post_sender_workers = max(32, min(128, computed_post_workers))
        self.post_queue_max_size = max(1, post_queue_max_size)
        self.post_connect_timeout_seconds = max(0.1, post_connect_timeout_seconds)
        self.post_pool_timeout_seconds = max(0.1, post_pool_timeout_seconds)
        self.post_max_http_connections = (
            max(1, int(post_max_http_connections)) if post_max_http_connections is not None else 500
        )
        self.post_max_keepalive_connections = (
            max(1, int(post_max_keepalive_connections))
            if post_max_keepalive_connections is not None
            else self.post_max_http_connections
        )
        self.post_max_inflight_requests = (
            max(1, int(post_max_inflight_requests)) if post_max_inflight_requests is not None else 500
        )
        self.suppress_httpx_request_logs = suppress_httpx_request_logs
        self.http2_enabled = http2_enabled

        self._event_queue: asyncio.Queue[_DispatchEvent | object] = asyncio.Queue(maxsize=self.max_queue_size)
        self._sql_queue: asyncio.Queue[_SqlDispatchItem | object] = asyncio.Queue(maxsize=self.sql_batch_max_queue_size)
        self._post_queue: asyncio.Queue[_PostDispatchItem | object] = asyncio.Queue(maxsize=self.post_queue_max_size)
        self._post_send_queue: asyncio.Queue[_PostBatchEnvelope | object] = asyncio.Queue(
            maxsize=self.post_queue_max_size
        )
        self._post_batches: dict[_PostBatchKey, list[_PostDispatchItem]] = {}
        self._sql_batches: dict[_SqlBatchKey, list[_SqlDispatchItem]] = {}
        self._sql_batch_task: asyncio.Task | None = None
        self._post_batch_task: asyncio.Task | None = None
        self._post_workers_tasks: list[asyncio.Task] = []
        self._inflight_events: dict[int, _DispatchEvent] = {}
        self._next_event_id = 1
        self._recent_processed_ids: set[int] = set()
        self._recent_processed_order: deque[int] = deque()
        self._recent_processed_limit = 100_000
        self._sql_success_log_counter = 0
        self._post_success_log_counter = 0
        self._workers: list[asyncio.Task] = []
        self._worker_events_processed: dict[int, int] = {}
        self._busy_workers = 0
        self._max_busy_workers = 0
        self._dispatches: list[dict[str, Any]] = []
        self._compiled_dispatches: list[_CompiledDispatch] = []
        self._dispatch_routes_by_event: dict[str, _DispatchRouteBucket] = {}
        self._dispatch_routes_any_event = _DispatchRouteBucket(post=[], sql=[])
        self._engines: dict[str, AsyncEngine] = {}
        self._sql_stmt_cache: dict[str, Any] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._post_inflight_semaphore: asyncio.Semaphore | None = None
        if self.post_max_inflight_requests and self.post_max_inflight_requests > 0:
            self._post_inflight_semaphore = asyncio.Semaphore(self.post_max_inflight_requests)

        self._started = False
        self._shutdown_started = False
        self._start_lock = asyncio.Lock()
        self._start_task: asyncio.Task | None = None

        self._stats: dict[str, int] = {
            "events_received": 0,
            "events_queued": 0,
            "events_dropped": 0,
            "events_processed": 0,
            "dispatches_attempted": 0,
            "dispatches_succeeded": 0,
            "dispatches_failed": 0,
            "post_batches_executed": 0,
            "post_rows_batched": 0,
            "sql_batches_executed": 0,
            "sql_rows_batched": 0,
        }

        Path(self.dispatches_path).mkdir(parents=True, exist_ok=True)
        if self.example_path:
            Path(self.example_path).mkdir(parents=True, exist_ok=True)

        self._finalizer = weakref.finalize(self, self._shutdown_sync, "finalizer")
        atexit.register(self._shutdown_sync, "atexit")
        self._register_signal_handlers()

    def _register_signal_handlers(self) -> None:
        try:
            self._previous_sigint_handler = signal.getsignal(signal.SIGINT)
            self._previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

            def _signal_handler(signum: int, frame: Any) -> None:
                signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
                logging.warning("Received %s, triggering dispatcher shutdown drain", signal_name)
                self._shutdown_sync(f"signal:{signal_name}")

                previous = self._previous_sigint_handler if signum == signal.SIGINT else self._previous_sigterm_handler
                if callable(previous):
                    previous(signum, frame)

            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            logging.debug("Could not register signal handlers for EventDispatcher", exc_info=True)

    def _shutdown_sync(self, reason: str = "unknown") -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True

        try:
            logging.info("EventDispatcher shutdown hook running (reason=%s)", reason)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(self.stop(drain=True))
                return

            asyncio.run(self._shutdown_async())
        except Exception:
            logging.exception("Failed during EventDispatcher shutdown hook")

    async def _shutdown_async(self) -> None:
        if self._started:
            workers_on_closed_loop = any(self._worker_loop_is_closed(worker) for worker in self._workers)

            if not workers_on_closed_loop:
                try:
                    await self.stop(drain=True)
                    return
                except Exception:
                    logging.exception("Graceful stop failed during shutdown, using fallback drain")

            self._workers = []
            self._started = False

        await self._drain_pending_events_fallback()
        await self._close_resources()

    def _worker_loop_is_closed(self, worker: asyncio.Task) -> bool:
        try:
            return worker.get_loop().is_closed()
        except Exception:
            return False

    async def _reinitialize_io_for_shutdown_loop(self) -> None:
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                logging.debug("Error closing previous HTTP client during shutdown reinit", exc_info=True)
            self._http_client = None

        if self._engines:
            for engine in self._engines.values():
                try:
                    await engine.dispose()
                except Exception:
                    logging.debug("Error disposing previous SQL engine during shutdown reinit", exc_info=True)
            self._engines.clear()

        self.reload_dispatches()
        self._http_client = self._create_http_client()
        self._ensure_post_batch_task_started()
        if not self._post_workers_tasks:
            fallback_workers = max(1, min(8, self.post_sender_workers))
            self._post_workers_tasks = [
                asyncio.create_task(
                    self._post_worker_loop(i + 1), name=f"event-dispatcher-fallback-post-worker-{i + 1}"
                )
                for i in range(fallback_workers)
            ]
        self._ensure_sql_batch_task_started()

    def _create_http_client(self) -> httpx.AsyncClient:
        if self.suppress_httpx_request_logs:
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)

        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.post_connect_timeout_seconds,
                read=self.http_timeout_seconds,
                write=self.http_timeout_seconds,
                pool=self.post_pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=self.post_max_keepalive_connections,
                max_connections=self.post_max_http_connections,
                keepalive_expiry=60.0,
            ),
            http2=self.http2_enabled,
        )

    async def _drain_pending_events_fallback(self) -> None:
        await self._reinitialize_io_for_shutdown_loop()

        pending_events: list[_DispatchEvent] = []
        pending_seen_ids: set[int] = set()
        while True:
            try:
                item = self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                if item is _STOP:
                    continue
                if isinstance(item, _DispatchEvent):
                    if item.event_id not in pending_seen_ids:
                        pending_seen_ids.add(item.event_id)
                        pending_events.append(item)
            finally:
                try:
                    self._event_queue.task_done()
                except Exception:
                    pass

        if self._inflight_events:
            for event in self._inflight_events.values():
                if event.event_id not in pending_seen_ids:
                    pending_seen_ids.add(event.event_id)
                    pending_events.append(event)
            self._inflight_events.clear()

        drained = 0
        for event in pending_events:
            try:
                if not self._was_already_processed(event.event_id):
                    await self._process_event(event)
                    self._mark_processed(event.event_id)
                    drained += 1
            except Exception:
                logging.exception("Failed while fallback-processing event")

        if drained:
            logging.info("Fallback drain completed; processed queued events=%s", drained)

        await self._post_queue.join()
        await self._flush_all_post_batches()
        await self._post_send_queue.join()
        await self._sql_queue.join()
        await self._flush_all_sql_batches()

    async def _close_resources(self) -> None:
        await self._stop_post_batch_task(drain=False)
        await self._stop_post_workers(drain=False)
        await self._stop_sql_batch_task(drain=False)

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()

        self._workers = []
        self._started = False
        self._start_task = None

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return

            self.reload_dispatches()
            self._http_client = self._create_http_client()

            self._workers = [
                asyncio.create_task(self._worker_loop(i + 1), name=f"event-dispatcher-worker-{i + 1}")
                for i in range(self.max_workers)
            ]
            self._post_workers_tasks = [
                asyncio.create_task(self._post_worker_loop(i + 1), name=f"event-dispatcher-post-worker-{i + 1}")
                for i in range(self.post_sender_workers)
            ]
            self._ensure_post_batch_task_started()
            self._ensure_sql_batch_task_started()
            self._started = True
            logging.info(
                "EventDispatcher started with event_workers=%s post_batch_enabled=%s post_batch_size=%s post_sender_workers=%s post_max_http_connections=%s post_max_inflight_requests=%s queue_size=%s sql_batch_enabled=%s sql_batch_size=%s dispatches=%s",
                self.max_workers,
                self.post_batch_enabled,
                self.post_batch_size,
                self.post_sender_workers,
                self.post_max_http_connections,
                self.post_max_inflight_requests,
                self.max_queue_size,
                self.sql_batch_enabled,
                self.sql_batch_size,
                len(self._dispatches),
            )

    def _ensure_start_task(self) -> None:
        if self._started:
            return
        if self._start_task is None or self._start_task.done():
            self._start_task = asyncio.create_task(self.start())

    async def stop(self, drain: bool = True) -> None:
        if not self._started:
            return

        if drain:
            await self.flush()

        await self._stop_post_batch_task(drain=drain)
        await self._stop_post_workers(drain=drain)
        await self._stop_sql_batch_task(drain=drain)

        for _ in self._workers:
            await self._event_queue.put(_STOP)

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._post_workers_tasks = []

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()

        self._started = False
        self._start_task = None
        logging.info("EventDispatcher stopped")

    async def flush(self, timeout: float | None = None) -> None:
        if timeout is None:
            await self._event_queue.join()
            await self._post_queue.join()
            await self._flush_all_post_batches()
            await self._post_send_queue.join()
            await self._sql_queue.join()
            await self._flush_all_sql_batches()
            return
        await asyncio.wait_for(self._event_queue.join(), timeout=timeout)
        await asyncio.wait_for(self._post_queue.join(), timeout=timeout)
        await asyncio.wait_for(self._flush_all_post_batches(), timeout=timeout)
        await asyncio.wait_for(self._post_send_queue.join(), timeout=timeout)
        await asyncio.wait_for(self._sql_queue.join(), timeout=timeout)
        await asyncio.wait_for(self._flush_all_sql_batches(), timeout=timeout)

    def _ensure_post_batch_task_started(self) -> None:
        if self._post_batch_task is None or self._post_batch_task.done():
            self._post_batch_task = asyncio.create_task(self._post_batch_loop(), name="event-dispatcher-post-batcher")

    async def _stop_post_batch_task(self, drain: bool) -> None:
        if self._post_batch_task is None:
            if drain:
                await self._flush_all_post_batches()
            return

        if drain:
            await self._post_queue.join()
            await self._flush_all_post_batches()

        await self._post_queue.put(_STOP)
        await asyncio.gather(self._post_batch_task, return_exceptions=True)
        self._post_batch_task = None

    async def _stop_post_workers(self, drain: bool) -> None:
        if not self._post_workers_tasks:
            return

        if drain:
            await self._post_send_queue.join()

        for _ in self._post_workers_tasks:
            await self._post_send_queue.put(_STOP)

        await asyncio.gather(*self._post_workers_tasks, return_exceptions=True)
        self._post_workers_tasks = []

    def _ensure_sql_batch_task_started(self) -> None:
        if not self.sql_batch_enabled:
            return
        if self._sql_batch_task is None or self._sql_batch_task.done():
            self._sql_batch_task = asyncio.create_task(self._sql_batch_loop(), name="event-dispatcher-sql-batcher")

    async def _stop_sql_batch_task(self, drain: bool) -> None:
        if not self.sql_batch_enabled:
            return

        if self._sql_batch_task is None:
            if drain:
                await self._flush_all_sql_batches()
            return

        if drain:
            await self._sql_queue.join()
            await self._flush_all_sql_batches()

        await self._sql_queue.put(_STOP)
        await asyncio.gather(self._sql_batch_task, return_exceptions=True)
        self._sql_batch_task = None

    async def _post_batch_loop(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(self._post_queue.get(), timeout=self.post_batch_flush_interval_seconds)
            except TimeoutError:
                await self._flush_all_post_batches()
                continue

            if item is _STOP:
                self._post_queue.task_done()
                await self._flush_all_post_batches()
                return

            assert isinstance(item, _PostDispatchItem)
            key = self._make_post_batch_key(item)
            batch = self._post_batches.setdefault(key, [])
            batch.append(item)
            if not self.post_batch_enabled or len(batch) >= self.post_batch_size:
                await self._flush_post_batch(key)

    async def _flush_all_post_batches(self) -> None:
        if not self._post_batches:
            return

        keys = list(self._post_batches.keys())
        for key in keys:
            await self._flush_post_batch(key)

    async def _flush_post_batch(self, key: _PostBatchKey) -> None:
        batch = self._post_batches.get(key)
        if not batch:
            return

        envelope = _PostBatchEnvelope(
            key=key,
            items=batch,
            queued_at=batch[0].queued_at,
        )

        await self._post_send_queue.put(envelope)
        for _ in batch:
            self._post_queue.task_done()
        self._post_batches.pop(key, None)

    async def _sql_batch_loop(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(
                    self._sql_queue.get(),
                    timeout=self.sql_batch_flush_interval_seconds,
                )
            except TimeoutError:
                await self._flush_all_sql_batches()
                continue

            if item is _STOP:
                self._sql_queue.task_done()
                await self._flush_all_sql_batches()
                return

            assert isinstance(item, _SqlDispatchItem)
            batch = self._sql_batches.setdefault(item.key, [])
            batch.append(item)
            if len(batch) >= self.sql_batch_size:
                await self._flush_sql_batch(item.key)

    async def _flush_all_sql_batches(self) -> None:
        if not self._sql_batches:
            return

        keys = list(self._sql_batches.keys())
        for key in keys:
            await self._flush_sql_batch(key)

    async def _flush_sql_batch(self, key: _SqlBatchKey) -> None:
        batch = self._sql_batches.get(key)
        if not batch:
            return

        params_list = [item.params for item in batch]
        row_count = len(params_list)
        start = time.monotonic()

        try:
            await self._run_with_retry(
                lambda: self._dispatch_sql_many(key.connection_string, key.query, params_list),
                retry_attempts=key.retry_attempts,
                backoff_seconds=key.backoff_seconds,
            )
            self._stats["dispatches_succeeded"] += row_count
            self._stats["sql_rows_batched"] += row_count
            self._stats["sql_batches_executed"] += 1
            if self._should_log_sql_success():
                logging.info(
                    "SQL batch dispatch result: %r",
                    {
                        "type": "sql-batch",
                        "connection_string": key.connection_string,
                        "query": key.query,
                        "rows": row_count,
                        "sample_params": params_list[0] if params_list else None,
                        "latency": time.monotonic() - start,
                    },
                )
        except Exception:
            self._stats["dispatches_failed"] += row_count
            logging.exception(
                "SQL batch dispatch failed: %r",
                {
                    "connection_string": key.connection_string,
                    "query": key.query,
                    "rows": row_count,
                    "sample_params": params_list[0] if params_list else None,
                    "latency": time.monotonic() - start,
                },
            )
        finally:
            for _ in batch:
                self._sql_queue.task_done()
            self._sql_batches.pop(key, None)

    def reload_dispatches(self) -> None:
        dispatches: list[dict[str, Any]] = []
        compiled_dispatches: list[_CompiledDispatch] = []
        dispatch_routes_by_event: dict[str, _DispatchRouteBucket] = {}
        dispatch_routes_any_event = _DispatchRouteBucket(post=[], sql=[])
        sql_connection_strings: set[str] = set()

        for file_path in Path(self.dispatches_path).glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    content = json.load(file)

                if not isinstance(content, dict):
                    logging.warning("Skipping dispatch %s because root JSON is not an object", file_path.name)
                    continue

                dispatches.append(content)

                plan = self._compile_dispatch(content, source_name=file_path.name)
                if plan is None:
                    continue

                compiled_dispatches.append(plan)

                if plan.dispatch_type == "sql" and plan.sql_key_static is not None:
                    sql_connection_strings.add(plan.sql_key_static.connection_string)

                if plan.on_event_static:
                    bucket = dispatch_routes_by_event.setdefault(
                        plan.on_event_static, _DispatchRouteBucket(post=[], sql=[])
                    )
                else:
                    bucket = dispatch_routes_any_event

                if plan.dispatch_type == "sql":
                    bucket.sql.append(plan)
                else:
                    bucket.post.append(plan)
            except Exception:
                logging.exception("Failed to parse dispatch JSON file: %s", file_path.name)

        old_keys = set(self._engines.keys())
        for key in old_keys - sql_connection_strings:
            try:
                engine = self._engines.pop(key)
                dispose_coro = engine.dispose()
                if asyncio.iscoroutine(dispose_coro):
                    try:
                        asyncio.create_task(dispose_coro)
                    except Exception:
                        pass
            except Exception:
                logging.exception("Error disposing SQL engine for: %s", key)

        for key in sql_connection_strings - old_keys:
            try:
                self._engines[key] = create_async_engine(
                    key,
                    pool_pre_ping=True,
                    pool_size=20,
                    max_overflow=30,
                    pool_recycle=1800,
                    future=True,
                )
            except Exception:
                logging.exception("Error creating SQL engine for: %s", key)

        self._dispatches = dispatches
        self._compiled_dispatches = compiled_dispatches
        self._dispatch_routes_by_event = dispatch_routes_by_event
        self._dispatch_routes_any_event = dispatch_routes_any_event
        self._sql_stmt_cache.clear()

        post_count = sum(len(bucket.post) for bucket in dispatch_routes_by_event.values()) + len(
            dispatch_routes_any_event.post
        )
        sql_count = sum(len(bucket.sql) for bucket in dispatch_routes_by_event.values()) + len(
            dispatch_routes_any_event.sql
        )
        logging.info(
            "Loaded %s dispatch file(s), routes post=%s sql=%s, SQL pools=%s",
            len(self._dispatches),
            post_count,
            sql_count,
            len(self._engines),
        )

    def _compile_dispatch(self, content: dict[str, Any], source_name: str) -> _CompiledDispatch | None:
        try:
            self._validate_dispatch_content(content)
        except Exception:
            logging.exception("Invalid dispatch content in %s", source_name)
            return None

        dispatch_type = str(content.get("dispatch_type", "")).lower()
        retry_attempts = max(1, int(content.get("retry_attempts", self.default_retry_attempts)))
        backoff_seconds = float(content.get("retry_backoff_seconds", self.default_retry_backoff_seconds))

        on_event_renderer, on_event_is_static, on_event_static_value = self._build_value_renderer(
            content.get("on_event")
        )
        on_event_static: str | None = None
        if on_event_is_static and isinstance(on_event_static_value, str) and on_event_static_value:
            on_event_static = on_event_static_value

        compiled_filters: list[_CompiledFilter] = []
        for filter_item in content.get("filters", []):
            if not isinstance(filter_item, dict):
                continue
            key_renderer, _, _ = self._build_value_renderer(filter_item.get("key"))
            value_renderer, _, _ = self._build_value_renderer(filter_item.get("value"))
            compiled_filters.append(
                _CompiledFilter(
                    key_renderer=key_renderer,
                    value_renderer=value_renderer,
                    operator=str(filter_item.get("operator", "eq")).lower(),
                )
            )

        url_renderer: Callable[[dict[str, Any]], Any] | None = None
        headers_renderer: Callable[[dict[str, Any]], Any] | None = None
        body_renderer: Callable[[dict[str, Any]], Any] | None = None
        connection_renderer: Callable[[dict[str, Any]], Any] | None = None
        query_renderer: Callable[[dict[str, Any]], Any] | None = None
        params_renderer: Callable[[dict[str, Any]], Any] | None = None
        sql_key_static: _SqlBatchKey | None = None

        if dispatch_type == "post":
            url_renderer, _, _ = self._build_value_renderer(content.get("url"))
            headers_renderer, _, _ = self._build_value_renderer(content.get("headers", {}))
            body_renderer, _, _ = self._build_value_renderer(content.get("body", {}))
        elif dispatch_type == "sql":
            connection_renderer, connection_is_static, connection_static = self._build_value_renderer(
                content.get("connection_string")
            )
            query_renderer, query_is_static, query_static = self._build_value_renderer(content.get("query"))
            params_renderer, _, _ = self._build_value_renderer(content.get("params", {}))

            if (
                connection_is_static
                and query_is_static
                and isinstance(connection_static, str)
                and isinstance(query_static, str)
            ):
                sql_key_static = _SqlBatchKey(
                    connection_string=self._normalize_async_connection_string(connection_static),
                    query=query_static,
                    retry_attempts=retry_attempts,
                    backoff_seconds=backoff_seconds,
                )
        else:
            logging.warning("Skipping unsupported dispatch_type=%s in %s", dispatch_type, source_name)
            return None

        return _CompiledDispatch(
            source_name=source_name,
            dispatch_type=dispatch_type,
            on_event_renderer=on_event_renderer,
            on_event_static=on_event_static,
            filters=tuple(compiled_filters),
            retry_attempts=retry_attempts,
            backoff_seconds=backoff_seconds,
            url_renderer=url_renderer,
            headers_renderer=headers_renderer,
            body_renderer=body_renderer,
            connection_renderer=connection_renderer,
            query_renderer=query_renderer,
            params_renderer=params_renderer,
            sql_key_static=sql_key_static,
        )

    def _build_value_renderer(self, value: Any) -> tuple[Callable[[dict[str, Any]], Any], bool, Any]:
        if isinstance(value, dict):
            compiled_items = []
            all_static = True
            static_dict: dict[str, Any] = {}
            for key, item in value.items():
                key_renderer, key_static, key_static_value = self._build_value_renderer(key)
                val_renderer, val_static, val_static_value = self._build_value_renderer(item)
                compiled_items.append((key_renderer, val_renderer))
                all_static = all_static and key_static and val_static
                if all_static:
                    static_dict[str(key_static_value)] = val_static_value

            if all_static:
                frozen = copy.deepcopy(static_dict)
                return (lambda _context, frozen=frozen: frozen), True, frozen

            frozen_items = tuple(compiled_items)

            def _render_dict(context: dict[str, Any], items: tuple[Any, ...] = frozen_items) -> dict[str, Any]:
                rendered: dict[str, Any] = {}
                for key_renderer, val_renderer in items:
                    rendered_key = key_renderer(context)
                    rendered[str(rendered_key)] = val_renderer(context)
                return rendered

            return _render_dict, False, None

        if isinstance(value, list):
            compiled_items = [self._build_value_renderer(item) for item in value]
            if all(item[1] for item in compiled_items):
                frozen = [item[2] for item in compiled_items]
                return (lambda _context, frozen=frozen: frozen), True, frozen

            frozen_items = tuple(item[0] for item in compiled_items)

            def _render_list(context: dict[str, Any], items: tuple[Any, ...] = frozen_items) -> list[Any]:
                return [item(context) for item in items]

            return _render_list, False, None

        if isinstance(value, tuple):
            compiled_items = [self._build_value_renderer(item) for item in value]
            if all(item[1] for item in compiled_items):
                frozen = tuple(item[2] for item in compiled_items)
                return (lambda _context, frozen=frozen: frozen), True, frozen

            frozen_items = tuple(item[0] for item in compiled_items)

            def _render_tuple(context: dict[str, Any], items: tuple[Any, ...] = frozen_items) -> tuple[Any, ...]:
                return tuple(item(context) for item in items)

            return _render_tuple, False, None

        if not isinstance(value, str):
            return (lambda _context, value=value: value), True, value

        is_single_token, parts = self._compile_template(value)
        if is_single_token:
            _, token = parts[0]

            def _render_single(context: dict[str, Any], token: str = token) -> Any:
                return self._resolve_placeholder(token, context)

            return _render_single, False, None

        if len(parts) == 1 and parts[0][0] == "lit":
            literal = parts[0][1]
            return (lambda _context, literal=literal: literal), True, literal

        def _render_template(context: dict[str, Any], parts: tuple[tuple[str, str], ...] = parts) -> str:
            out_parts: list[str] = []
            for kind, token_or_text in parts:
                if kind == "lit":
                    out_parts.append(token_or_text)
                    continue
                resolved = self._resolve_placeholder(token_or_text, context)
                out_parts.append("" if resolved is None else str(resolved))
            return "".join(out_parts)

        return _render_template, False, None

    async def add_async(self, name: str, event_type: str, data: Any = None) -> bool:
        self._stats["events_received"] += 1

        try:
            if not self._started:
                await self.start()

            event = _DispatchEvent(
                event_id=self._allocate_event_id(),
                name=name,
                event_type=event_type,
                data=data,
                queued_at=time.monotonic(),
            )

            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                if self.add_timeout_seconds <= 0:
                    raise
                await asyncio.wait_for(self._event_queue.put(event), timeout=self.add_timeout_seconds)

            self._stats["events_queued"] += 1
            if self.enable_enqueue_logs:
                logging.info("Event added to queue: name=%s event_type=%s data=%s", name, event_type, data)
            return True
        except asyncio.QueueFull:
            self._stats["events_dropped"] += 1
            logging.warning("Dispatcher queue full; dropping event %s/%s", name, event_type)
            return False
        except TimeoutError:
            self._stats["events_dropped"] += 1
            logging.warning("Timed out while queueing event %s/%s", name, event_type)
            return False
        except Exception:
            self._stats["events_dropped"] += 1
            logging.exception("Unexpected error while queueing event %s/%s", name, event_type)
            return False

    def add(self, name: str, event_type: str, data: Any = None) -> bool:
        self._stats["events_received"] += 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._stats["events_dropped"] += 1
            logging.error(
                "EventDispatcher.add called without a running asyncio loop. "
                "Use add_async in synchronous contexts. Event dropped: %s/%s",
                name,
                event_type,
            )
            return False

        try:
            if not self._started:
                self._ensure_start_task()

            event = _DispatchEvent(
                event_id=self._allocate_event_id(),
                name=name,
                event_type=event_type,
                data=data,
                queued_at=time.monotonic(),
            )
            self._event_queue.put_nowait(event)
            self._stats["events_queued"] += 1
            return True
        except asyncio.QueueFull:
            self._stats["events_dropped"] += 1
            logging.warning("Dispatcher queue full; dropping event %s/%s", name, event_type)
            return False
        except Exception:
            self._stats["events_dropped"] += 1
            logging.exception("Unexpected error while queueing event %s/%s", name, event_type)
            return False

    def get_stats(self) -> dict[str, int]:
        stats = dict(self._stats)
        stats["queue_size"] = self._event_queue.qsize()
        stats["post_queue_size"] = self._post_queue.qsize()
        stats["post_send_queue_size"] = self._post_send_queue.qsize()
        stats["sql_queue_size"] = self._sql_queue.qsize()
        stats["dispatches_loaded"] = len(self._dispatches)
        stats["workers_configured"] = self.max_workers
        stats["workers_running"] = len(self._workers)
        stats["post_batch_enabled"] = int(self.post_batch_enabled)
        stats["post_batch_size"] = self.post_batch_size
        stats["post_workers_configured"] = self.post_workers
        stats["post_sender_workers_configured"] = self.post_sender_workers
        stats["post_workers_running"] = len(self._post_workers_tasks)
        stats["post_worker_concurrency"] = self.post_worker_concurrency
        stats["post_max_http_connections"] = self.post_max_http_connections
        stats["post_max_inflight_requests"] = self.post_max_inflight_requests
        stats["workers_busy_current"] = self._busy_workers
        stats["workers_busy_peak"] = self._max_busy_workers
        stats["workers_with_activity"] = sum(1 for total in self._worker_events_processed.values() if total > 0)
        return stats

    def get_dispatch_names(self) -> list[str]:
        try:
            return sorted(
                [
                    file.name
                    for file in Path(self.dispatches_path).iterdir()
                    if file.is_file() and file.suffix == ".json"
                ]
            )
        except Exception:
            logging.exception("Failed to list dispatch files")
            return []

    def get_dispatch_content(self, name: str) -> dict | None:
        try:
            file_path = self._dispatch_file_path(name)
            with open(file_path, "r", encoding="utf-8") as file:
                content = json.load(file)
            return content if isinstance(content, dict) else None
        except FileNotFoundError:
            logging.warning("Dispatch file not found: %s", name)
            return None
        except Exception:
            logging.exception("Failed to read dispatch file: %s", name)
            return None

    def create_dispatch(
        self,
        name: str,
        content: dict[str, Any],
        *,
        overwrite: bool = False,
        validate: bool = True,
    ) -> bool:
        try:
            if validate:
                self._validate_dispatch_content(content)

            file_path = self._dispatch_file_path(name)
            if file_path.exists() and not overwrite:
                logging.warning("Dispatch already exists and overwrite=False: %s", file_path.name)
                return False

            self._write_json_file(file_path, content)
            self.reload_dispatches()
            logging.info("Dispatch created: %s", file_path.name)
            return True
        except Exception:
            logging.exception("Failed to create dispatch: %s", name)
            return False

    def edit_dispatch(
        self,
        name: str,
        content: dict[str, Any],
        *,
        merge: bool = True,
        validate: bool = True,
    ) -> bool:
        try:
            file_path = self._dispatch_file_path(name)
            if not file_path.exists():
                logging.warning("Dispatch not found for edit: %s", file_path.name)
                return False

            with open(file_path, "r", encoding="utf-8") as file:
                current_content = json.load(file)

            if not isinstance(current_content, dict):
                logging.error("Dispatch root JSON must be object for edit: %s", file_path.name)
                return False

            updated_content = self._deep_merge_dict(current_content, content) if merge else copy.deepcopy(content)

            if validate:
                self._validate_dispatch_content(updated_content)

            self._write_json_file(file_path, updated_content)
            self.reload_dispatches()
            logging.info("Dispatch edited: %s", file_path.name)
            return True
        except Exception:
            logging.exception("Failed to edit dispatch: %s", name)
            return False

    def delete_dispatch(self, name: str, *, missing_ok: bool = True) -> bool:
        try:
            file_path = self._dispatch_file_path(name)
            if not file_path.exists():
                if missing_ok:
                    logging.info("Dispatch already absent: %s", file_path.name)
                    return True
                logging.warning("Dispatch not found for delete: %s", file_path.name)
                return False

            file_path.unlink()
            self.reload_dispatches()
            logging.info("Dispatch deleted: %s", file_path.name)
            return True
        except Exception:
            logging.exception("Failed to delete dispatch: %s", name)
            return False

    def _normalize_dispatch_filename(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Dispatch name cannot be empty")

        if any(sep in normalized for sep in ("/", "\\")):
            raise ValueError("Dispatch name must not contain path separators")

        if normalized in {".", ".."}:
            raise ValueError("Invalid dispatch filename")

        if not normalized.endswith(".json"):
            normalized = f"{normalized}.json"

        return normalized

    def _dispatch_file_path(self, name: str) -> Path:
        filename = self._normalize_dispatch_filename(name)
        base_dir = Path(self.dispatches_path).resolve()
        file_path = (base_dir / filename).resolve()

        try:
            file_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError("Dispatch path escapes dispatches directory") from exc

        return file_path

    def _write_json_file(self, file_path: Path, content: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=4)
        tmp_path.replace(file_path)

    def _deep_merge_dict(self, current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(current)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dict(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def _validate_dispatch_content(self, content: dict[str, Any]) -> None:
        if not isinstance(content, dict):
            raise ValueError("Dispatch JSON root must be an object")

        dispatch_type = content.get("dispatch_type")
        if dispatch_type not in {"post", "sql"}:
            raise ValueError("dispatch_type must be 'post' or 'sql'")

        on_event = content.get("on_event")
        if not isinstance(on_event, str) or not on_event.strip():
            raise ValueError("on_event must be a non-empty string")

        filters = content.get("filters", [])
        if not isinstance(filters, list):
            raise ValueError("filters must be a list")
        for item in filters:
            if not isinstance(item, dict):
                raise ValueError("each filters item must be an object")
            if "operator" in item and not isinstance(item["operator"], str):
                raise ValueError("filter operator must be a string")

        if dispatch_type == "post":
            url = content.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("post dispatch requires a non-empty url")
            headers = content.get("headers", {})
            if headers is not None and not isinstance(headers, dict):
                raise ValueError("headers must be an object when provided")

        if dispatch_type == "sql":
            connection_string = content.get("connection_string")
            query = content.get("query")
            params = content.get("params", {})
            if not isinstance(connection_string, str) or not connection_string.strip():
                raise ValueError("sql dispatch requires connection_string")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("sql dispatch requires query")
            if not isinstance(params, dict):
                raise ValueError("sql dispatch params must be an object")

    def get_example_names(self) -> list[str]:
        if not self.example_path:
            return []
        try:
            return [f.name for f in Path(self.example_path).iterdir() if f.is_file() and f.suffix == ".json"]
        except Exception:
            return []

    def get_example_content(self, name: str) -> dict | None:
        if not self.example_path:
            return None
        try:
            file_path = Path(self.example_path) / name
            with open(file_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return None

    async def _worker_loop(self, worker_id: int) -> None:
        logging.debug("Dispatcher worker %s started", worker_id)
        self._worker_events_processed.setdefault(worker_id, 0)
        while True:
            item = await self._event_queue.get()
            current_event: _DispatchEvent | None = None
            worker_busy = False
            try:
                if item is _STOP:
                    return
                assert isinstance(item, _DispatchEvent)
                current_event = item
                self._inflight_events[id(item)] = item
                self._busy_workers += 1
                worker_busy = True
                if self._busy_workers > self._max_busy_workers:
                    self._max_busy_workers = self._busy_workers
                if not self._was_already_processed(item.event_id):
                    await self._process_event(item)
                    self._mark_processed(item.event_id)
                self._worker_events_processed[worker_id] += 1
            except Exception:
                logging.exception("Worker %s failed while processing event", worker_id)
            finally:
                if worker_busy and self._busy_workers > 0:
                    self._busy_workers -= 1
                if current_event is not None:
                    self._inflight_events.pop(id(current_event), None)
                self._event_queue.task_done()

    async def _process_event(self, event: _DispatchEvent) -> None:
        self._stats["events_processed"] += 1

        context = {
            "name": event.name,
            "event_type": event.event_type,
            "data": event.data,
        }

        event_bucket = self._dispatch_routes_by_event.get(event.event_type)
        if event_bucket is not None:
            await self._process_route_bucket(event_bucket, context)

        await self._process_route_bucket(self._dispatch_routes_any_event, context)

    async def _process_route_bucket(self, bucket: _DispatchRouteBucket, context: dict[str, Any]) -> None:
        for plan in bucket.post:
            await self._process_single_dispatch(plan, context)

        for plan in bucket.sql:
            await self._process_single_dispatch(plan, context)

    async def _process_single_dispatch(self, plan: _CompiledDispatch, context: dict[str, Any]) -> None:
        try:
            if not self._event_matches_plan(plan, context):
                return

            self._stats["dispatches_attempted"] += 1

            if plan.dispatch_type == "post":
                await self._enqueue_post_dispatch(plan, context)
                return

            if self.sql_batch_enabled:
                await self._enqueue_sql_dispatch(plan, context)
            else:
                await self._run_with_retry(
                    lambda: self._dispatch_sql_plan(plan, context),
                    retry_attempts=plan.retry_attempts,
                    backoff_seconds=plan.backoff_seconds,
                )
                self._stats["dispatches_succeeded"] += 1
        except Exception:
            self._stats["dispatches_failed"] += 1
            logging.exception("Dispatch failed (source=%s type=%s)", plan.source_name, plan.dispatch_type)

    async def _enqueue_post_dispatch(self, plan: _CompiledDispatch, context: dict[str, Any]) -> None:
        if plan.url_renderer is None:
            raise ValueError("POST dispatch url renderer is required")

        url = plan.url_renderer(context)
        headers = plan.headers_renderer(context) if plan.headers_renderer is not None else {}
        body = plan.body_renderer(context) if plan.body_renderer is not None else {}

        if not isinstance(url, str) or not url.strip():
            raise ValueError("POST dispatch requires a valid url")
        if headers is not None and not isinstance(headers, dict):
            raise ValueError("POST dispatch headers must be an object")

        item = _PostDispatchItem(
            source_name=plan.source_name,
            retry_attempts=plan.retry_attempts,
            backoff_seconds=plan.backoff_seconds,
            url=url,
            headers=headers,
            body=body,
            queued_at=time.monotonic(),
        )

        try:
            self._post_queue.put_nowait(item)
        except asyncio.QueueFull:
            if self.add_timeout_seconds <= 0:
                raise
            await asyncio.wait_for(self._post_queue.put(item), timeout=self.add_timeout_seconds)

    def _make_post_batch_key(self, item: _PostDispatchItem) -> _PostBatchKey:
        headers_json = orjson.dumps(item.headers or {}, option=orjson.OPT_SORT_KEYS).decode("utf-8")
        return _PostBatchKey(
            source_name=item.source_name,
            url=item.url,
            headers_json=headers_json,
            retry_attempts=item.retry_attempts,
            backoff_seconds=item.backoff_seconds,
        )

    async def _post_worker_loop(self, worker_id: int) -> None:
        logging.debug("Dispatcher post worker %s started", worker_id)
        while True:
            envelope = await self._post_send_queue.get()
            try:
                if envelope is _STOP:
                    return

                assert isinstance(envelope, _PostBatchEnvelope)
                await self._run_with_retry(
                    lambda: self._dispatch_post_envelope(envelope),
                    retry_attempts=envelope.key.retry_attempts,
                    backoff_seconds=envelope.key.backoff_seconds,
                )
                self._stats["dispatches_succeeded"] += len(envelope.items)
                self._stats["post_rows_batched"] += len(envelope.items)
                self._stats["post_batches_executed"] += 1
            except (httpx.ConnectTimeout, httpx.PoolTimeout):
                self._stats["dispatches_failed"] += (
                    len(envelope.items) if isinstance(envelope, _PostBatchEnvelope) else 1
                )
                if isinstance(envelope, _PostBatchEnvelope):
                    logging.warning(
                        "POST dispatch timeout (source=%s url=%s batch_size=%s)",
                        envelope.key.source_name,
                        envelope.key.url,
                        len(envelope.items),
                    )
            except Exception:
                self._stats["dispatches_failed"] += (
                    len(envelope.items) if isinstance(envelope, _PostBatchEnvelope) else 1
                )
                logging.exception("POST dispatch failed")
            finally:
                self._post_send_queue.task_done()

    async def _enqueue_sql_dispatch(self, plan: _CompiledDispatch, context: dict[str, Any]) -> None:
        if plan.params_renderer is None:
            raise ValueError("SQL dispatch params renderer is required")

        params = plan.params_renderer(context)
        if not isinstance(params, dict):
            raise ValueError("SQL dispatch params must be an object")

        if plan.sql_key_static is not None:
            sql_key = plan.sql_key_static
        else:
            if plan.connection_renderer is None or plan.query_renderer is None:
                raise ValueError("SQL dispatch connection/query renderer is required")
            connection_string = plan.connection_renderer(context)
            query = plan.query_renderer(context)
            if not isinstance(connection_string, str) or not connection_string.strip():
                raise ValueError("SQL dispatch requires connection_string")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("SQL dispatch requires query")
            sql_key = _SqlBatchKey(
                connection_string=self._normalize_async_connection_string(connection_string),
                query=query,
                retry_attempts=plan.retry_attempts,
                backoff_seconds=plan.backoff_seconds,
            )

        self._ensure_sql_batch_task_started()
        item = _SqlDispatchItem(
            key=sql_key,
            params=params,
            queued_at=time.monotonic(),
        )

        try:
            self._sql_queue.put_nowait(item)
        except asyncio.QueueFull:
            if self.add_timeout_seconds <= 0:
                raise
            await asyncio.wait_for(self._sql_queue.put(item), timeout=self.add_timeout_seconds)

    def _event_matches_plan(self, plan: _CompiledDispatch, context: dict[str, Any]) -> bool:
        try:
            if plan.on_event_static is not None:
                if plan.on_event_static != context["event_type"]:
                    return False
            else:
                dispatch_event = plan.on_event_renderer(context)
                if isinstance(dispatch_event, str) and dispatch_event and dispatch_event != context["event_type"]:
                    return False

            for filter_item in plan.filters:
                key = filter_item.key_renderer(context)
                value = filter_item.value_renderer(context)
                if not self._evaluate_filter_values(key, value, filter_item.operator):
                    return False

            return True
        except Exception:
            logging.exception("Error evaluating compiled dispatch filters (source=%s)", plan.source_name)
            return False

    def _allocate_event_id(self) -> int:
        event_id = self._next_event_id
        self._next_event_id += 1
        return event_id

    def _was_already_processed(self, event_id: int) -> bool:
        return event_id in self._recent_processed_ids

    def _mark_processed(self, event_id: int) -> None:
        if event_id in self._recent_processed_ids:
            return
        self._recent_processed_ids.add(event_id)
        self._recent_processed_order.append(event_id)

        if len(self._recent_processed_order) > self._recent_processed_limit:
            oldest = self._recent_processed_order.popleft()
            self._recent_processed_ids.discard(oldest)

    def _should_log_sql_success(self) -> bool:
        if not self.enable_dispatch_success_logs:
            return False

        self._sql_success_log_counter += 1
        if self._sql_success_log_counter <= self.success_log_first_n:
            return True
        return self._sql_success_log_counter % self.success_log_every_n == 0

    def _should_log_post_success(self) -> bool:
        if not self.enable_post_success_logs:
            return False

        self._post_success_log_counter += 1
        if self._post_success_log_counter <= self.success_log_first_n:
            return True
        return self._post_success_log_counter % self.success_log_every_n == 0

    def _truncate_text(self, value: str | None, max_len: int = 500) -> str | None:
        if value is None:
            return None
        if len(value) <= max_len:
            return value
        return f"{value[:max_len]}...<truncated:{len(value) - max_len}>"

    def _evaluate_filter_values(self, key: Any, value: Any, operator: str) -> bool:
        if operator == "eq":
            return key == value
        if operator == "ne":
            return key != value
        if operator == "in":
            return key in value if isinstance(value, (list, tuple, set)) else False
        if operator == "not_in":
            return key not in value if isinstance(value, (list, tuple, set)) else False
        if operator == "gt":
            return self._safe_compare(key, value, "gt")
        if operator == "lt":
            return self._safe_compare(key, value, "lt")
        if operator == "gte":
            return self._safe_compare(key, value, "gte")
        if operator == "lte":
            return self._safe_compare(key, value, "lte")
        if operator == "contains":
            if isinstance(key, str):
                return str(value) in key
            if isinstance(key, (list, tuple, set, dict)):
                return value in key
            return False

        logging.warning("Unsupported filter operator: %s", operator)
        return False

    def _safe_compare(self, left: Any, right: Any, op: str) -> bool:
        try:
            if op == "gt":
                return left > right
            if op == "lt":
                return left < right
            if op == "gte":
                return left >= right
            if op == "lte":
                return left <= right
            return False
        except Exception:
            return False

    async def _run_with_retry(self, operation: Any, retry_attempts: int, backoff_seconds: float) -> None:
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

    async def _dispatch_post_envelope(self, envelope: _PostBatchEnvelope) -> None:
        if self._http_client is None:
            raise RuntimeError("HTTP client not initialized")

        batch_size = len(envelope.items)
        if batch_size == 0:
            return

        start = time.monotonic()
        queued_for = max(0.0, time.monotonic() - envelope.queued_at)

        if self.post_batch_enabled:
            payload: Any = [item.body for item in envelope.items]
        else:
            payload = envelope.items[0].body

        headers: dict[str, str] = {}
        for key, value in (envelope.items[0].headers or {}).items():
            headers[str(key)] = str(value)
        headers.setdefault("Content-Type", "application/json")

        body_bytes = orjson.dumps(payload)

        log_dict = {
            "type": "post",
            "source": envelope.key.source_name,
            "url": envelope.key.url,
            "batch_size": batch_size,
            "queued_for": queued_for,
        }

        try:
            if self._post_inflight_semaphore is not None:
                async with self._post_inflight_semaphore:
                    response = await self._http_client.post(envelope.key.url, headers=headers, content=body_bytes)
            else:
                response = await self._http_client.post(envelope.key.url, headers=headers, content=body_bytes)
            latency = time.monotonic() - start
            response.raise_for_status()
            if self._should_log_post_success():
                response_preview = bytes(response.content[:200]) if response.content else b""
                log_dict.update(
                    {
                        "status": response.status_code,
                        "latency": latency,
                        "response_preview": response_preview.decode("utf-8", errors="ignore"),
                    }
                )
                logging.info("POST dispatch result: %r", log_dict)
        except httpx.TimeoutException as exc:
            latency = time.monotonic() - start
            log_dict.update({"error": f"TIMEOUT: {exc}", "latency": latency})
            logging.error("POST dispatch result: %r", log_dict)
            raise
        except httpx.HTTPStatusError as exc:
            latency = time.monotonic() - start
            log_dict.update(
                {
                    "error": f"HTTP ERROR: {exc}",
                    "status": getattr(exc.response, "status_code", None),
                    "latency": latency,
                    "response": getattr(exc.response, "text", None),
                }
            )
            logging.error("POST dispatch result: %r", log_dict)
            raise
        except Exception as exc:
            latency = time.monotonic() - start
            log_dict.update({"error": f"FAILED: {exc}", "latency": latency})
            logging.error("POST dispatch result: %r", log_dict)
            raise

    async def _dispatch_sql_plan(self, plan: _CompiledDispatch, context: dict[str, Any]) -> None:
        if plan.params_renderer is None:
            raise ValueError("SQL dispatch params renderer is required")

        params = plan.params_renderer(context)
        if plan.sql_key_static is not None:
            connection_string = plan.sql_key_static.connection_string
            query = plan.sql_key_static.query
        else:
            if plan.connection_renderer is None or plan.query_renderer is None:
                raise ValueError("SQL dispatch connection/query renderer is required")
            connection_string = plan.connection_renderer(context)
            query = plan.query_renderer(context)

        if not isinstance(connection_string, str) or not connection_string.strip():
            raise ValueError("SQL dispatch requires connection_string")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("SQL dispatch requires query")
        if not isinstance(params, dict):
            raise ValueError("SQL dispatch params must be an object")

        engine = self._get_or_create_engine(connection_string)
        log_dict = {
            "type": "sql",
            "source": plan.source_name,
            "connection_string": connection_string,
            "query": query,
            "params": params,
        }
        start = time.monotonic()
        stmt = self._get_sql_statement(query)

        try:
            async with engine.connect() as conn:
                result = await conn.execute(stmt, params)
                await conn.commit()
            if self._should_log_sql_success():
                latency = time.monotonic() - start
                log_dict.update(
                    {
                        "latency": latency,
                        "rowcount": getattr(result, "rowcount", None),
                        "result": str(result),
                    }
                )
                logging.info("SQL dispatch result: %r", log_dict)
        except SQLAlchemyError as exc:
            latency = time.monotonic() - start
            log_dict.update({"error": f"FAILED: {exc}", "latency": latency})
            logging.error("SQL dispatch result: %r", log_dict)
            raise

    async def _dispatch_sql_many(
        self,
        connection_string: str,
        query: str,
        params_list: list[dict[str, Any]],
    ) -> None:
        if not params_list:
            return

        engine = self._get_or_create_engine(connection_string)
        stmt = self._get_sql_statement(query)
        async with engine.connect() as conn:
            await conn.execute(stmt, params_list)
            await conn.commit()

    def _get_or_create_engine(self, connection_string: str) -> AsyncEngine:
        normalized = self._normalize_async_connection_string(connection_string)
        engine = self._engines.get(normalized)
        if engine is None:
            engine = create_async_engine(
                normalized,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=30,
                pool_recycle=1800,
                future=True,
            )
            self._engines[normalized] = engine
        return engine

    def _get_sql_statement(self, query: str) -> Any:
        stmt = self._sql_stmt_cache.get(query)
        if stmt is None:
            stmt = text(query)
            self._sql_stmt_cache[query] = stmt
        return stmt

    def _normalize_async_connection_string(self, connection_string: str) -> str:
        value = connection_string.strip()
        if "+" in value.split("://", maxsplit=1)[0]:
            return value

        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("mysql://"):
            return value.replace("mysql://", "mysql+aiomysql://", 1)
        if value.startswith("sqlite://"):
            return value.replace("sqlite://", "sqlite+aiosqlite://", 1)

        return value

    def _render_value(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            rendered: dict[str, Any] = {}
            for key, item in value.items():
                rendered_key = self._render_value(key, context)
                rendered[str(rendered_key)] = self._render_value(item, context)
            return rendered

        if isinstance(value, list):
            return [self._render_value(item, context) for item in value]

        if isinstance(value, tuple):
            return tuple(self._render_value(item, context) for item in value)

        if not isinstance(value, str):
            return value

        is_single_token, parts = self._compile_template(value)
        if is_single_token:
            _, token = parts[0]
            return self._resolve_placeholder(token, context)

        out_parts: list[str] = []
        for kind, token_or_text in parts:
            if kind == "lit":
                out_parts.append(token_or_text)
                continue
            resolved = self._resolve_placeholder(token_or_text, context)
            out_parts.append("" if resolved is None else str(resolved))
        return "".join(out_parts)

    @staticmethod
    @lru_cache(maxsize=8192)
    def _compile_template(value: str) -> tuple[bool, tuple[tuple[str, str], ...]]:
        full_match = _PLACEHOLDER_PATTERN.fullmatch(value)
        if value.startswith("{") and value.endswith("}") and full_match:
            return True, (("token", full_match.group(1).strip()),)

        parts: list[tuple[str, str]] = []
        last_index = 0
        for match in _PLACEHOLDER_PATTERN.finditer(value):
            if match.start() > last_index:
                parts.append(("lit", value[last_index : match.start()]))
            parts.append(("token", match.group(1).strip()))
            last_index = match.end()

        if last_index < len(value):
            parts.append(("lit", value[last_index:]))

        if not parts:
            parts.append(("lit", value))

        return False, tuple(parts)

    def _resolve_placeholder(self, token: str, context: dict[str, Any]) -> Any:
        if token == "name":
            return context.get("name")
        if token == "event_type":
            return context.get("event_type")
        if token == "data":
            return context.get("data")

        data_key_match = _DATA_KEY_PATTERN.match(token)
        if data_key_match:
            data = context.get("data")
            key = data_key_match.group(1)
            if isinstance(data, dict):
                return data.get(key)
            return None

        return None
