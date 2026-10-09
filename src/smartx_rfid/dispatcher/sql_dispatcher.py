import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import oracledb
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


logger = logging.getLogger(__name__)


try:
    oracledb.init_oracle_client()
    logger.info("Oracle client initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize Oracle client: {e}")


_STOP = object()


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

    async def enqueue(self, item: _SqlItem, add_timeout: float = 0.2) -> None:
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            if add_timeout <= 0:
                raise
            await asyncio.wait_for(self._queue.put(item), timeout=add_timeout)

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


__all__ = ["SqlDispatcher", "_SqlBatchKey", "_SqlItem"]
