"""
event_dispatcher.py
-------------------
Async event dispatcher that routes named events to HTTP POST, SQL, MQTT, or MongoDB destinations
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

MQTT:
    {
        "dispatch_type": "mqtt",
        "on_event": "user.created",
        "host": "localhost",
        "port": 1883,
        "topic": "smartx/events/{event_type}",
        "qos": 1,
        "retain": false,
        "payload": {"name": "{name}", "data": "{data}"},
        "allow_batches": true,
        "batch_size": 500,
        "flush_interval_seconds": 0.1,
        "retry_attempts": 3,
        "retry_backoff_seconds": 0.25
    }

MONGODB:
    {
        "dispatch_type": "mongodb",
        "on_event": "user.created",
        "connection_string": "mongodb://localhost:27017",
        "database": "smartx",
        "collection": "events",
        "ordered": true,
        "document": {"name": "{name}", "event_type": "{event_type}", "data": "{data}"},
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

from .http_dispatcher import HttpDispatcher, _PostItem
from .mongo_dispatcher import MongoDispatcher, _MongoBatchKey, _MongoItem
from .mqtt_dispatcher import MqttDispatcher, _MqttBatchKey, _MqttItem
from .sql_dispatcher import SqlDispatcher, _SqlBatchKey, _SqlItem


logger = logging.getLogger(__name__)

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
    mqtt_key_fn: Callable[[dict[str, Any]], _MqttBatchKey] | None
    mqtt_payload_fn: Callable[[dict[str, Any]], Any] | None
    mqtt_key_static: _MqttBatchKey | None
    mongo_key_fn: Callable[[dict[str, Any]], _MongoBatchKey] | None
    mongo_doc_fn: Callable[[dict[str, Any]], Any] | None
    mongo_key_static: _MongoBatchKey | None


@dataclass
class _RouteBucket:
    post: list[_CompiledDispatch] = field(default_factory=list)
    sql: list[_CompiledDispatch] = field(default_factory=list)
    mqtt: list[_CompiledDispatch] = field(default_factory=list)
    mongo: list[_CompiledDispatch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EventDispatcher — main coordinator
# ---------------------------------------------------------------------------


class EventDispatcher:
    """
    Async event dispatcher. Routes events to HTTP POST, SQL, MQTT, or MongoDB targets based on
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
    mqtt : MqttDispatcher | None
        Optional pre-configured MqttDispatcher. Creates a default one if omitted.
    mongo : MongoDispatcher | None
        Optional pre-configured MongoDispatcher. Creates a default one if omitted.

    Custom tuning example
    ---------------------
        dispatcher = EventDispatcher(
            dispatches_path="dispatches/",
            sql=SqlDispatcher(batch_size=200, flush_interval_seconds=0.1),
            http=HttpDispatcher(batch_size=100, sender_workers=32),
            mqtt=MqttDispatcher(batch_size=100, sender_workers=16),
            mongo=MongoDispatcher(batch_size=200, sender_workers=16),
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
        mqtt: "MqttDispatcher | None" = None,
        mongo: "MongoDispatcher | None" = None,
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
        self._mqtt = mqtt or MqttDispatcher()
        self._mongo = mongo or MongoDispatcher()

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
            self._mqtt.start()
            self._mongo.start()
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
        await self._mqtt.stop(drain=drain)
        await self._mongo.stop(drain=drain)
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
            await self._mqtt.flush()
            await self._mongo.flush()

        if timeout is None:
            await _flush_all()
        else:
            await asyncio.wait_for(_flush_all(), timeout=timeout)

    # ------------------------------------------------------------------
    # Public API — add events
    # ------------------------------------------------------------------

    async def add_async(self, name: str, event_type: str, data: Any = None, verbose: bool = False) -> bool:
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
            if verbose:
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

    def add(self, name: str, event_type: str, data: Any = None, verbose: bool = False) -> bool:
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
            if verbose:
                logger.info("Event enqueued | name=%s event_type=%s data=%s", name, event_type, data)
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
        stats["mqtt_batch_size"] = self._mqtt.batch_size
        stats["mqtt_sender_workers"] = self._mqtt.sender_workers
        stats["mongo_batch_size"] = self._mongo.batch_size
        stats["mongo_sender_workers"] = self._mongo.sender_workers
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
                if plan.dispatch_type == "sql":
                    bucket.sql.append(plan)
                elif plan.dispatch_type == "post":
                    bucket.post.append(plan)
                elif plan.dispatch_type == "mqtt":
                    bucket.mqtt.append(plan)
                elif plan.dispatch_type == "mongodb":
                    bucket.mongo.append(plan)
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
        mqtt_count = sum(len(b.mqtt) for b in routes_by_event.values()) + len(routes_any.mqtt)
        mongo_count = sum(len(b.mongo) for b in routes_by_event.values()) + len(routes_any.mongo)
        logger.info(
            "Dispatches reloaded | files=%d post_routes=%d sql_routes=%d mqtt_routes=%d mongo_routes=%d sql_pools=%d",
            len(compiled),
            post_count,
            sql_count,
            mqtt_count,
            mongo_count,
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
        for plan in bucket.mqtt if bucket else []:
            await self._dispatch_one(plan, ctx)
        for plan in bucket.mongo if bucket else []:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.post:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.sql:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.mqtt:
            await self._dispatch_one(plan, ctx)
        for plan in self._routes_any.mongo:
            await self._dispatch_one(plan, ctx)

    async def _dispatch_one(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        try:
            if not self._matches(plan, ctx):
                return
            self._stats["dispatches_attempted"] += 1
            if plan.dispatch_type == "post":
                await self._enqueue_post(plan, ctx)
            elif plan.dispatch_type == "sql":
                await self._enqueue_sql(plan, ctx)
            elif plan.dispatch_type == "mqtt":
                await self._enqueue_mqtt(plan, ctx)
            elif plan.dispatch_type == "mongodb":
                await self._enqueue_mongo(plan, ctx)
            else:
                raise ValueError(f"Unsupported dispatch_type: {plan.dispatch_type}")
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

    async def _enqueue_mqtt(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        payload = plan.mqtt_payload_fn(ctx) if plan.mqtt_payload_fn else {}
        key = plan.mqtt_key_static or (plan.mqtt_key_fn(ctx) if plan.mqtt_key_fn else None)
        if key is None:
            raise ValueError("MQTT dispatch key was not compiled")
        await self._mqtt.enqueue(_MqttItem(key=key, payload=payload, queued_at=time.monotonic()))

    async def _enqueue_mongo(self, plan: _CompiledDispatch, ctx: dict[str, Any]) -> None:
        document = plan.mongo_doc_fn(ctx) if plan.mongo_doc_fn else {}
        key = plan.mongo_key_static or (plan.mongo_key_fn(ctx) if plan.mongo_key_fn else None)
        if key is None:
            raise ValueError("MongoDB dispatch key was not compiled")
        await self._mongo.enqueue(_MongoItem(key=key, document=document, queued_at=time.monotonic()))

    def _build_mqtt_key(
        self,
        *,
        source: str,
        host_value: Any,
        port_value: Any,
        topic_value: Any,
        username_value: Any,
        password_value: Any,
        client_id_value: Any,
        keepalive_value: Any,
        qos_value: Any,
        retain_value: Any,
        batch_size: int,
        allow_batches: bool,
        flush_interval_seconds: float,
        retry_attempts: int,
        backoff_seconds: float,
    ) -> _MqttBatchKey:
        host = str(host_value).strip() if host_value is not None else ""
        topic = str(topic_value).strip() if topic_value is not None else ""
        if not host:
            raise ValueError("MQTT dispatch requires host")
        if not topic:
            raise ValueError("MQTT dispatch requires topic")

        port = self._coerce_positive_int(port_value, default=1883)
        keepalive = self._coerce_positive_int(keepalive_value, default=60)
        qos = self._coerce_int_in_range(qos_value, default=0, minimum=0, maximum=2)
        retain = self._coerce_bool(retain_value, default=False)

        username = None if username_value in (None, "") else str(username_value)
        password = None if password_value in (None, "") else str(password_value)
        client_id = None if client_id_value in (None, "") else str(client_id_value)

        return _MqttBatchKey(
            source=source,
            host=host,
            port=port,
            topic=topic,
            username=username,
            password=password,
            client_id=client_id,
            keepalive_seconds=keepalive,
            qos=qos,
            retain=retain,
            batch_size=batch_size,
            allow_batches=allow_batches,
            flush_interval_seconds=flush_interval_seconds,
            retry_attempts=retry_attempts,
            backoff_seconds=backoff_seconds,
        )

    @staticmethod
    def _build_mongo_key(
        *,
        source: str,
        connection_string_value: Any,
        database_value: Any,
        collection_value: Any,
        ordered_value: Any,
        batch_size: int,
        allow_batches: bool,
        flush_interval_seconds: float,
        retry_attempts: int,
        backoff_seconds: float,
    ) -> _MongoBatchKey:
        connection_string = str(connection_string_value).strip() if connection_string_value is not None else ""
        database = str(database_value).strip() if database_value is not None else ""
        collection = str(collection_value).strip() if collection_value is not None else ""

        if not connection_string:
            raise ValueError("MongoDB dispatch requires connection_string")
        if not database:
            raise ValueError("MongoDB dispatch requires database")
        if not collection:
            raise ValueError("MongoDB dispatch requires collection")

        ordered = ordered_value if isinstance(ordered_value, bool) else True

        return _MongoBatchKey(
            source=source,
            connection_string=connection_string,
            database=database,
            collection=collection,
            ordered=ordered,
            batch_size=batch_size,
            allow_batches=allow_batches,
            flush_interval_seconds=flush_interval_seconds,
            retry_attempts=retry_attempts,
            backoff_seconds=backoff_seconds,
        )

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
        default_batch_size = (
            self._http.batch_size
            if dtype == "post"
            else self._sql.batch_size
            if dtype == "sql"
            else self._mqtt.batch_size
            if dtype == "mqtt"
            else self._mongo.batch_size
        )
        default_flush = (
            self._http.flush_interval_seconds
            if dtype == "post"
            else self._sql.flush_interval_seconds
            if dtype == "sql"
            else self._mqtt.flush_interval_seconds
            if dtype == "mqtt"
            else self._mongo.flush_interval_seconds
        )

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
            mqtt_key_fn=None,
            mqtt_payload_fn=None,
            mqtt_key_static=None,
            mongo_key_fn=None,
            mongo_doc_fn=None,
            mongo_key_static=None,
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
        elif dtype == "mqtt":
            host_fn, host_static, host_val = self._build_renderer(content.get("host"))
            port_fn, port_static, port_val = self._build_renderer(content.get("port", 1883))
            topic_fn, topic_static, topic_val = self._build_renderer(content.get("topic"))
            username_fn, username_static, username_val = self._build_renderer(content.get("username"))
            password_fn, password_static, password_val = self._build_renderer(content.get("password"))
            client_id_fn, client_id_static, client_id_val = self._build_renderer(content.get("client_id"))
            keepalive_fn, keepalive_static, keepalive_val = self._build_renderer(content.get("keepalive_seconds", 60))
            qos_fn, qos_static, qos_val = self._build_renderer(content.get("qos", 0))
            retain_fn, retain_static, retain_val = self._build_renderer(content.get("retain", False))
            plan.mqtt_payload_fn = self._build_renderer(content.get("payload", {}))[0]

            if all(
                (
                    host_static,
                    port_static,
                    topic_static,
                    username_static,
                    password_static,
                    client_id_static,
                    keepalive_static,
                    qos_static,
                    retain_static,
                )
            ):
                plan.mqtt_key_static = self._build_mqtt_key(
                    source=source,
                    host_value=host_val,
                    port_value=port_val,
                    topic_value=topic_val,
                    username_value=username_val,
                    password_value=password_val,
                    client_id_value=client_id_val,
                    keepalive_value=keepalive_val,
                    qos_value=qos_val,
                    retain_value=retain_val,
                    batch_size=batch_size,
                    allow_batches=allow_batches,
                    flush_interval_seconds=dispatch_flush,
                    retry_attempts=retry,
                    backoff_seconds=backoff,
                )
            else:

                def _mqtt_key_builder(
                    ctx: dict[str, Any],
                    _host_fn: Callable[[dict[str, Any]], Any] = host_fn,
                    _port_fn: Callable[[dict[str, Any]], Any] = port_fn,
                    _topic_fn: Callable[[dict[str, Any]], Any] = topic_fn,
                    _username_fn: Callable[[dict[str, Any]], Any] = username_fn,
                    _password_fn: Callable[[dict[str, Any]], Any] = password_fn,
                    _client_id_fn: Callable[[dict[str, Any]], Any] = client_id_fn,
                    _keepalive_fn: Callable[[dict[str, Any]], Any] = keepalive_fn,
                    _qos_fn: Callable[[dict[str, Any]], Any] = qos_fn,
                    _retain_fn: Callable[[dict[str, Any]], Any] = retain_fn,
                ) -> _MqttBatchKey:
                    return self._build_mqtt_key(
                        source=source,
                        host_value=_host_fn(ctx),
                        port_value=_port_fn(ctx),
                        topic_value=_topic_fn(ctx),
                        username_value=_username_fn(ctx),
                        password_value=_password_fn(ctx),
                        client_id_value=_client_id_fn(ctx),
                        keepalive_value=_keepalive_fn(ctx),
                        qos_value=_qos_fn(ctx),
                        retain_value=_retain_fn(ctx),
                        batch_size=batch_size,
                        allow_batches=allow_batches,
                        flush_interval_seconds=dispatch_flush,
                        retry_attempts=retry,
                        backoff_seconds=backoff,
                    )

                plan.mqtt_key_fn = _mqtt_key_builder
        elif dtype == "mongodb":
            conn_fn, conn_static, conn_val = self._build_renderer(content.get("connection_string"))
            db_fn, db_static, db_val = self._build_renderer(content.get("database"))
            coll_fn, coll_static, coll_val = self._build_renderer(content.get("collection"))
            ordered_fn, ordered_static, ordered_val = self._build_renderer(content.get("ordered", True))

            plan.mongo_doc_fn = self._build_renderer(content.get("document", {}))[0]

            if conn_static and db_static and coll_static and ordered_static:
                plan.mongo_key_static = self._build_mongo_key(
                    source=source,
                    connection_string_value=conn_val,
                    database_value=db_val,
                    collection_value=coll_val,
                    ordered_value=ordered_val,
                    batch_size=batch_size,
                    allow_batches=allow_batches,
                    flush_interval_seconds=dispatch_flush,
                    retry_attempts=retry,
                    backoff_seconds=backoff,
                )
            else:

                def _mongo_key_builder(
                    ctx: dict[str, Any],
                    _conn_fn: Callable[[dict[str, Any]], Any] = conn_fn,
                    _db_fn: Callable[[dict[str, Any]], Any] = db_fn,
                    _coll_fn: Callable[[dict[str, Any]], Any] = coll_fn,
                    _ordered_fn: Callable[[dict[str, Any]], Any] = ordered_fn,
                ) -> _MongoBatchKey:
                    return EventDispatcher._build_mongo_key(
                        source=source,
                        connection_string_value=_conn_fn(ctx),
                        database_value=_db_fn(ctx),
                        collection_value=_coll_fn(ctx),
                        ordered_value=_ordered_fn(ctx),
                        batch_size=batch_size,
                        allow_batches=allow_batches,
                        flush_interval_seconds=dispatch_flush,
                        retry_attempts=retry,
                        backoff_seconds=backoff,
                    )

                plan.mongo_key_fn = _mongo_key_builder
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
        if dtype not in ("post", "sql", "mqtt", "mongodb"):
            raise ValueError("dispatch_type must be 'post', 'sql', 'mqtt', or 'mongodb'")
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
        if dtype == "mqtt":
            host = content.get("host")
            topic = content.get("topic")
            if not isinstance(host, str) or not host.strip():
                raise ValueError("mqtt dispatch requires a non-empty host")
            if not isinstance(topic, str) or not topic.strip():
                raise ValueError("mqtt dispatch requires a non-empty topic")

            if "port" in content:
                try:
                    port = int(content["port"])
                except (TypeError, ValueError):
                    raise ValueError("mqtt port must be an integer") from None
                if port <= 0:
                    raise ValueError("mqtt port must be greater than zero")

            if "qos" in content:
                try:
                    qos = int(content["qos"])
                except (TypeError, ValueError):
                    raise ValueError("mqtt qos must be an integer") from None
                if qos not in (0, 1, 2):
                    raise ValueError("mqtt qos must be 0, 1, or 2")

            if "retain" in content and not isinstance(content["retain"], bool):
                raise ValueError("mqtt retain must be a boolean")

            for key in ("username", "password", "client_id"):
                if key in content and content[key] is not None and not isinstance(content[key], str):
                    raise ValueError(f"mqtt {key} must be a string when provided")

            if "keepalive_seconds" in content:
                try:
                    keepalive = int(content["keepalive_seconds"])
                except (TypeError, ValueError):
                    raise ValueError("mqtt keepalive_seconds must be an integer") from None
                if keepalive <= 0:
                    raise ValueError("mqtt keepalive_seconds must be greater than zero")

        if dtype == "mongodb":
            for fname in ("connection_string", "database", "collection"):
                value = content.get(fname)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"mongodb dispatch requires non-empty {fname}")

            if "ordered" in content and not isinstance(content["ordered"], bool):
                raise ValueError("mongodb ordered must be a boolean")

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
    def _coerce_int_in_range(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(minimum, min(maximum, parsed))

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
