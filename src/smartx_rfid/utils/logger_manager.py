import asyncio
import json
import logging
import queue
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.sqltypes import String as SAString

from smartx_rfid.db import DatabaseManager
from smartx_rfid.db._main import DatabaseError
from smartx_rfid.models.log import Logs

_STANDARD_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "getMessage",
    "taskName",
    "message",  # set on the record by formatters of other handlers
    "asctime",
}

_DB_WORKER_THREAD_NAME = "LogDatabaseThread"


def _extract_extra(record: logging.LogRecord) -> Dict[str, Any]:
    """Return the JSON-safe custom fields (``extra=...``) attached to a log record."""
    extras: Dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_FIELDS:
            continue
        try:
            json.dumps(value)
            extras[key] = value
        except (TypeError, ValueError):
            extras[key] = str(value)
    return extras


class JsonQueueHandler(logging.Handler):
    """
    Handler that pushes logs to a queue for asynchronous JSON writing.
    Includes module, function, and thread info automatically.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "thread": record.threadName,
                "pathname": record.pathname,
            }

            if record.exc_info:
                log_entry["exception"] = logging.Formatter().formatException(record.exc_info)

            # Include extra fields
            log_entry.update(_extract_extra(record))

            self.log_queue.put_nowait(json.dumps(log_entry, ensure_ascii=False))

        except queue.Full:
            pass
        except Exception:
            self.handleError(record)

    def handleError(self, record):
        super().handleError(record)
        try:
            error_entry = {
                "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
                "level": "ERROR",
                "logger": record.name,
                "message": "Logging handler error",
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "thread": record.threadName,
                "exception": logging.Formatter().formatException(record.exc_info)
                if record.exc_info
                else "Handler error",
            }
            self.log_queue.put_nowait(json.dumps(error_entry, ensure_ascii=False))
        except Exception:
            pass


class DatabaseQueueHandler(logging.Handler):
    """
    Handler that hands log records to ``LoggerManager`` for asynchronous, batched
    database writing. It never blocks the caller and never touches the database.
    """

    def __init__(self, manager: "LoggerManager"):
        super().__init__()
        self._manager = manager

    def emit(self, record: logging.LogRecord):
        try:
            self._manager._enqueue_db_record(record)
        except Exception:
            self.handleError(record)


class _DatabaseWorkerNoiseFilter(logging.Filter):
    """Hides routine (< WARNING) records emitted by the database worker thread itself."""

    def __init__(self, manager: "LoggerManager"):
        super().__init__()
        self._manager = manager

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.thread == self._manager._db_thread_ident and record.levelno < logging.WARNING)


class LoggerManager:
    """
    Professional logger with console output, daily-rotated JSONL files and/or
    batched database logging. Everything is written asynchronously through queues,
    so logging calls never block on disk or network.

    Destinations (can be combined):
        - File system: enabled when ``log_path`` is given (or when no database is configured).
        - Database: enabled when ``database_url`` or ``database_manager`` is given.

    Database logging is resilient: connection problems never raise into the application,
    rows are buffered (bounded) and inserted in batches with ``DatabaseManager.bulk_insert``,
    retrying with exponential backoff while the database is unavailable.
    """

    def __init__(
        self,
        log_path: Optional[str] = None,
        base_filename: Optional[str] = None,
        storage_days: int = 7,
        *,
        database_url: Optional[str] = None,
        database_manager: Optional[DatabaseManager] = None,
        database_model: Optional[Type[DeclarativeBase]] = None,
        db_batch_size: int = 100,
        db_flush_interval: float = 2.0,
        db_queue_size: int = 10_000,
        db_storage_days: Optional[int] = None,
        db_level: int = logging.INFO,
    ):
        """
        Args:
            log_path: Directory for JSONL log files.
            base_filename: File name suffix. Defaults to the executed script name.
            storage_days: Delete daily log files older than this many days. 0 keeps only
                today's file; negative values keep all files.
            database_url: Database URL; a ``DatabaseManager`` is created and owned by the logger.
            database_manager: Existing ``DatabaseManager`` (not closed by ``close()``).
            database_model: SQLAlchemy model used to store logs. Defaults to ``Logs``.
                Only columns that exist in the model are filled.
            db_batch_size: Maximum rows per bulk insert.
            db_flush_interval: Maximum seconds a row waits before being inserted.
            db_queue_size: Maximum buffered rows. When exceeded, logs are dropped instead of blocking.
            db_storage_days: Delete database logs older than this many days. Defaults to
                ``storage_days``; 0 keeps only logs from today; negative values keep all.
            db_level: Minimum level persisted in the database.
        """
        if database_url and database_manager is not None:
            raise ValueError("Provide either 'database_url' or 'database_manager', not both")
        if db_batch_size < 1 or db_queue_size < 1 or db_flush_interval <= 0:
            raise ValueError("db_batch_size, db_queue_size and db_flush_interval must be positive")

        self.db_enabled = bool(database_url) or database_manager is not None
        self.file_enabled = log_path is not None or not self.db_enabled

        self.storage_days = storage_days
        self.current_date = datetime.now(timezone.utc).astimezone().date()
        self._closed = False

        # File system attributes
        self.base_filename = (base_filename or self._detect_script_name()) if self.file_enabled else base_filename
        self.default_log_path = (Path.cwd() / "logs").resolve()
        self.log_path: Optional[Path] = None
        self.filename: Optional[str] = None
        self.log_queue: Optional[queue.Queue] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        # Database attributes
        self.db_manager: Optional[DatabaseManager] = None
        self.db_model: Optional[Type[DeclarativeBase]] = None
        self.db_batch_size = db_batch_size
        self.db_flush_interval = db_flush_interval
        self.db_queue_size = db_queue_size
        self.db_storage_days = storage_days if db_storage_days is None else db_storage_days
        self.db_level = db_level
        self._owns_db = False
        self._db_columns: set = set()
        self._db_max_lengths: Dict[str, int] = {}
        self._db_queue: queue.Queue = queue.Queue(maxsize=db_queue_size)
        self._db_thread: Optional[threading.Thread] = None
        self._db_thread_ident: Optional[int] = None
        self._db_stop_event = threading.Event()
        self._db_ready = threading.Event()
        self._db_flush_requested = threading.Event()
        self._db_stats_lock = threading.Lock()
        self._db_stats = {"enqueued": 0, "inserted": 0, "dropped": 0, "overflow": 0, "failures": 0}

        self._file_handler: Optional[logging.Handler] = None
        self._db_handler: Optional[logging.Handler] = None
        self._console_handler: Optional[logging.Handler] = None

        # Resolve/validate everything that can fail before any thread is started.
        if self.file_enabled:
            requested_path = Path(log_path).expanduser().resolve() if log_path else self.default_log_path
            self.log_path = self._resolve_writable_log_path(requested_path)
            self.filename = self._get_filename_for_date(self.current_date)
        if self.db_enabled:
            self._init_database(database_url, database_manager, database_model)

        if self.file_enabled:
            self.log_queue = queue.Queue(maxsize=10_000)
            self.worker_thread = threading.Thread(target=self._worker, name="LogWriterThread", daemon=True)
            self.worker_thread.start()

        if self.db_enabled:
            self._db_thread = threading.Thread(target=self._db_worker, name=_DB_WORKER_THREAD_NAME, daemon=True)
            self._db_thread.start()
            self._db_thread_ident = self._db_thread.ident

        self._setup_logging()
        if self.file_enabled:
            self._cleanup_old_logs()  # Cleanup inicial seguro

        sys.excepthook = self._handle_exception
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._asyncio_exception_handler)
        except RuntimeError:
            pass

        destinations = []
        if self.file_enabled:
            destinations.append(f"file={self.filename}")
        if self.db_enabled:
            destinations.append(f"database={self.db_model.__tablename__}")
        logging.getLogger().info(f"Logger initialized: {', '.join(destinations)}")

    @staticmethod
    def _detect_script_name() -> str:
        """Name of the executed script (without extension), used as default log file name."""
        main_module = sys.modules.get("__main__")
        candidate = getattr(main_module, "__file__", None) or (sys.argv[0] if sys.argv else "")
        if not candidate or candidate in ("-c", "-m"):
            return "app"
        path = Path(candidate)
        name = path.stem
        if name == "__main__":  # python -m package
            name = path.resolve().parent.name
        name = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name).strip("._")
        return name or "app"

    # -------------------
    # Database setup
    # -------------------
    def _init_database(
        self,
        database_url: Optional[str],
        database_manager: Optional[DatabaseManager],
        database_model: Optional[Type[DeclarativeBase]],
    ):
        model = database_model or Logs
        table = getattr(model, "__table__", None)
        if table is None:
            raise ValueError(f"'{model!r}' is not a mapped SQLAlchemy model")

        columns = {c.key for c in table.columns}
        if not columns & {"level", "message", "timestamp"}:
            raise ValueError(f"Model '{model.__name__}' has none of the log columns: level, message, timestamp")

        if database_manager is not None:
            manager = database_manager
        else:
            manager = DatabaseManager(database_url=database_url, echo=False, pool_size=2, max_overflow=3)
            self._owns_db = True

        # Engine creation is lazy (no network I/O), so this is safe and surfaces bad URLs early.
        if manager.get_connection_info().get("status") == "not_initialized":
            manager.initialize()
        manager.register_models(model)

        self.db_manager = manager
        self.db_model = model
        self._db_columns = columns
        self._db_max_lengths = {
            c.key: c.type.length for c in table.columns if isinstance(c.type, SAString) and c.type.length
        }

    def _setup_db_tables(self) -> bool:
        """Create the log table (runs in the database worker). Returns True when ready."""
        try:
            self.db_manager.create_tables()
            table = self.db_model.__table__
            if not self.db_manager.table_exists(table.name):
                # Model lives in a different metadata than the manager's first model.
                table.metadata.create_all(bind=self.db_manager._engine, tables=[table], checkfirst=True)
            return True
        except Exception as e:
            logging.getLogger(__name__).warning(f"[LoggerManager] Database not ready, will retry: {e}")
            return False

    def _cleanup_old_db_logs(self) -> bool:
        if "timestamp" not in self._db_columns:
            return True
        try:
            now = datetime.now().astimezone()
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=self.db_storage_days)
            self.db_manager.delete_where(self.db_model, {"timestamp__lt": cutoff})
            return True
        except Exception as e:
            logging.getLogger(__name__).warning(f"[LoggerManager] Falha ao limpar logs antigos do banco: {e}")
            return False

    @staticmethod
    def _seconds_until_next_midnight() -> float:
        """Return the elapsed seconds until the next midnight in the local timezone."""
        now = datetime.now(timezone.utc).astimezone()
        tomorrow = now.date() + timedelta(days=1)
        midnight = datetime.combine(tomorrow, datetime.min.time()).astimezone()
        return (midnight.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds()

    # -------------------
    # Database queue / rows
    # -------------------
    def _bump(self, name: str, amount: int = 1):
        with self._db_stats_lock:
            self._db_stats[name] += amount

    def _build_db_row(self, record: logging.LogRecord) -> Dict[str, Any]:
        extra = _extract_extra(record)
        data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.threadName,
            "pathname": record.pathname,
            "exception": logging.Formatter().formatException(record.exc_info) if record.exc_info else None,
            "extra": json.dumps(extra, ensure_ascii=False) if extra else None,
        }
        row = {}
        for key, value in data.items():
            if key not in self._db_columns:
                continue
            max_len = self._db_max_lengths.get(key)
            if max_len and isinstance(value, str) and len(value) > max_len:
                value = value[:max_len]
            row[key] = value
        return row

    def _enqueue_db_record(self, record: logging.LogRecord):
        if record.thread == self._db_thread_ident:
            return  # never persist what the database worker itself logs (avoids feedback loops)
        row = self._build_db_row(record)
        try:
            self._db_queue.put_nowait(row)
            self._bump("enqueued")
        except queue.Full:
            self._bump("overflow")

    @staticmethod
    def _backoff(failures: int) -> float:
        return min(30.0, 0.5 * (2 ** min(max(failures - 1, 0), 6)))

    @staticmethod
    def _is_transient_db_error(exc: BaseException) -> bool:
        """True when the failure is about connectivity/availability (retry) rather than bad data."""
        err = exc
        while isinstance(err, DatabaseError) and err.original_error is not None:
            err = err.original_error
        if isinstance(err, DatabaseError):  # e.g. manager not initialized/closed
            return True
        if isinstance(err, (sa_exc.OperationalError, sa_exc.InterfaceError, sa_exc.TimeoutError)):
            return True
        return bool(getattr(err, "connection_invalidated", False))

    def _flush_db_batch(self, batch: List[Dict[str, Any]]) -> int:
        """
        Insert a batch using a single bulk insert.

        Returns:
            Number of rows consumed from the start of the batch (inserted or discarded as invalid).
            Less than ``len(batch)`` means the database is unavailable and the rest must be retried.
        """
        try:
            self.db_manager.bulk_insert(self.db_model, batch)
            self._bump("inserted", len(batch))
            return len(batch)
        except Exception as e:
            if self._is_transient_db_error(e):
                self._bump("failures")
                return 0

        # Bad data somewhere in the batch: isolate it so one poison row cannot block the queue.
        for index, row in enumerate(batch):
            try:
                self.db_manager.bulk_insert(self.db_model, [row])
                self._bump("inserted")
            except Exception as e:
                if self._is_transient_db_error(e):
                    self._bump("failures")
                    return index
                self._bump("dropped")
        return len(batch)

    def _drain_db_queue(self, pending: List[Dict[str, Any]], wait: bool):
        try:
            item = self._db_queue.get(timeout=0.25) if wait else self._db_queue.get_nowait()
        except queue.Empty:
            return
        pending.append(item)
        for _ in range(self.db_batch_size * 4):
            try:
                pending.append(self._db_queue.get_nowait())
            except queue.Empty:
                break

    def _discard_db_backlog(self, pending: List[Dict[str, Any]]):
        dropped = len(pending)
        pending.clear()
        while True:
            try:
                self._db_queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        if dropped:
            self._bump("dropped", dropped)

    def _db_worker(self):
        pending: List[Dict[str, Any]] = []
        pending_since: Optional[float] = None
        failures = 0
        retry_at = 0.0
        next_cleanup: Optional[float] = None
        cleanup_retry_seconds = 60.0

        while True:
            stopping = self._db_stop_event.is_set()
            try:
                self._drain_db_queue(pending, wait=not stopping)

                overflow = len(pending) - self.db_queue_size
                if overflow > 0:  # database unavailable for long: drop oldest instead of growing forever
                    del pending[:overflow]
                    self._bump("dropped", overflow)

                now = time.monotonic()
                if pending and pending_since is None:
                    pending_since = now

                round_failed = False

                if not self._db_ready.is_set() and (stopping or now >= retry_at):
                    if self._setup_db_tables():
                        failures, retry_at = 0, 0.0
                        cleanup_ok = self._cleanup_old_db_logs()
                        next_cleanup = time.monotonic() + (
                            self._seconds_until_next_midnight() if cleanup_ok else cleanup_retry_seconds
                        )
                        self._db_ready.set()
                    else:
                        failures += 1
                        retry_at = now + self._backoff(failures)
                        round_failed = True

                if self._db_ready.is_set() and (next_cleanup is None or now >= next_cleanup):
                    cleanup_ok = self._cleanup_old_db_logs()
                    next_cleanup = time.monotonic() + (
                        self._seconds_until_next_midnight() if cleanup_ok else cleanup_retry_seconds
                    )

                if self._db_ready.is_set() and pending and (stopping or now >= retry_at):
                    due = (
                        stopping
                        or self._db_flush_requested.is_set()
                        or len(pending) >= self.db_batch_size
                        or now - (pending_since or now) >= self.db_flush_interval
                    )
                    if due:
                        batch = pending[: self.db_batch_size]
                        consumed = self._flush_db_batch(batch)
                        del pending[:consumed]
                        if consumed == len(batch):
                            failures, retry_at = 0, 0.0
                        else:
                            failures += 1
                            retry_at = time.monotonic() + self._backoff(failures)
                            round_failed = True
                        pending_since = time.monotonic() if pending else None

                if not pending and self._db_queue.empty():
                    self._db_flush_requested.clear()

                if stopping:
                    if round_failed:
                        self._discard_db_backlog(pending)
                        break
                    if not pending and self._db_queue.empty():
                        break
            except Exception as e:  # the worker must never die
                print(f"[LoggerManager] Erro inesperado no worker do banco: {e}", file=sys.stderr)
                if stopping:
                    self._discard_db_backlog(pending)
                    break
                self._db_stop_event.wait(0.5)

    # -------------------
    # Public database helpers
    # -------------------
    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Wait until the database table is ready. Always True when database logging is disabled."""
        if not self.db_enabled:
            return True
        return self._db_ready.wait(timeout)

    def flush(self, timeout: float = 5.0) -> bool:
        """
        Force buffered database rows to be written and wait for completion.

        Returns:
            True when everything queued so far was processed within ``timeout``.
        """
        if not self.db_enabled:
            return True
        self._db_flush_requested.set()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._db_stats_lock:
                stats = self._db_stats
                if stats["inserted"] + stats["dropped"] >= stats["enqueued"]:
                    return True
            time.sleep(0.01)
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Database logging counters and state."""
        with self._db_stats_lock:
            stats = dict(self._db_stats)
        return {
            "db_enabled": self.db_enabled,
            "db_ready": self._db_ready.is_set(),
            "db_queue_size": self._db_queue.qsize(),
            "db_enqueued": stats["enqueued"],
            "db_inserted": stats["inserted"],
            "db_dropped": stats["dropped"] + stats["overflow"],
            "db_failures": stats["failures"],
        }

    @staticmethod
    def _coerce_datetime(value: Union[datetime, date, str]) -> datetime:
        """Convert datetime/date values or common date strings to ``datetime``."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if not isinstance(value, str):
            raise TypeError("Date filters must be datetime, date, or string values")

        text = value.strip()
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass

        for date_format in (
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S.%f",
            "%d-%m-%Y",
            "%d-%m-%Y %H:%M:%S",
            "%d.%m.%Y",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue

        raise ValueError(f"Invalid date value {value!r}. Use ISO format or a supported date such as '01/04/2026'.")

    def get_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        *,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        module: Optional[str] = None,
        message: Optional[str] = None,
        start_time: Optional[Union[datetime, date, str]] = None,
        end_time: Optional[Union[datetime, date, str]] = None,
        limit: int = 1000,
        offset: int = 0,
        order_by: Optional[str] = "timestamp",
        descending: bool = True,
    ) -> List[DeclarativeBase]:
        """Retrieve database logs with field filters and pagination.

        ``filters`` accepts the same operators as ``DatabaseManager.get_where``,
        for example ``{"level": "ERROR", "timestamp__gte": start}`` or
        ``{"message__ilike": "%timeout%"}``. Named arguments are shortcuts;
        ``message`` searches for a substring and the time arguments are inclusive.
        Results default to newest first.
        """
        if not self.db_enabled or self.db_manager is None or self.db_model is None:
            raise RuntimeError("Database logging is not enabled")
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset must be non-negative")
        if not self.wait_until_ready():
            raise RuntimeError("Log database is not ready")

        if start_time is not None:
            start_time = self._coerce_datetime(start_time)
        if end_time is not None:
            end_time = self._coerce_datetime(end_time)

        query_filters = dict(filters or {})
        for field, value in (("level", level), ("logger", logger), ("module", module)):
            if value is not None:
                query_filters[field] = value
        if message is not None:
            query_filters["message__contains"] = message
        if start_time is not None:
            query_filters["timestamp__gte"] = start_time
        if end_time is not None:
            query_filters["timestamp__lte"] = end_time

        with self.db_manager.get_session() as session:
            query = session.query(self.db_model)
            query = self.db_manager._apply_filters(query, self.db_model, query_filters)
            if order_by is not None:
                order_column = getattr(self.db_model, order_by, None)
                if order_column is None:
                    raise ValueError(f"Unknown log sort field: {order_by}")
                query = query.order_by(order_column.desc() if descending else order_column.asc())
            return query.offset(offset).limit(limit).all()

    # -------------------
    # Filename helpers
    # -------------------
    def _get_filename_for_date(self, day: date) -> str:
        return str(self.log_path / f"{day:%Y-%m-%d}_{self.base_filename}.jsonl")

    def _is_writable_path(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            with open(probe, "a", encoding="utf-8"):
                pass
            try:
                probe.unlink()
            except OSError:
                pass
            return True
        except Exception:
            return False

    def _resolve_writable_log_path(self, requested_path: Path) -> Path:
        for candidate in (requested_path, self.default_log_path):
            if self._is_writable_path(candidate):
                if candidate != requested_path:
                    print(
                        f"[LoggerManager] Sem permissão em '{requested_path}'. Usando fallback '{candidate}'.",
                        file=sys.stderr,
                    )
                return candidate

        # Last resort to keep application running even on strict environments.
        last_resort = Path("/tmp/logs").resolve()
        if self._is_writable_path(last_resort):
            print(
                f"[LoggerManager] Falha no path solicitado e no padrão. Usando fallback '{last_resort}'.",
                file=sys.stderr,
            )
            return last_resort

        raise PermissionError(
            f"Nenhum diretório de log gravável disponível: '{requested_path}', '{self.default_log_path}' e '{last_resort}'."
        )

    def _switch_to_default_path(self, failed_path: Path, error: Exception) -> bool:
        if failed_path == self.default_log_path:
            return False
        if not self._is_writable_path(self.default_log_path):
            return False
        self.log_path = self.default_log_path
        self.filename = self._get_filename_for_date(self.current_date)
        print(
            f"[LoggerManager] Falha ao escrever em '{failed_path}' ({error}). "
            f"Alternando para fallback '{self.default_log_path}'.",
            file=sys.stderr,
        )
        return True

    # -------------------
    # Worker for async writing
    # -------------------
    def _worker(self):
        next_cleanup = time.monotonic() + self._seconds_until_next_midnight()
        while not self.stop_event.is_set() or not self.log_queue.empty():
            try:
                msg = self.log_queue.get(timeout=0.5)
                try:
                    self._write(msg)
                except Exception as e:
                    logging.getLogger().error("Erro ao escrever log", exc_info=e)
            except queue.Empty:
                pass

            if time.monotonic() >= next_cleanup:
                self._cleanup_old_logs()
                next_cleanup = time.monotonic() + self._seconds_until_next_midnight()

    def _write(self, msg: str):
        today = datetime.now(timezone.utc).astimezone().date()
        if today != self.current_date:
            self.current_date = today
            self.filename = self._get_filename_for_date(today)
        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except (PermissionError, OSError) as e:
            failed_path = self.log_path
            if self._switch_to_default_path(failed_path=failed_path, error=e):
                with open(self.filename, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            else:
                raise

    # -------------------
    # Cleanup old logs
    # -------------------
    def _cleanup_old_logs(self):
        now = datetime.now().astimezone()
        cutoff_date = (
            now.replace(hour=0, minute=0, second=0, microsecond=0).date()
            if self.storage_days == 0
            else (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=self.storage_days)).date()
        )
        try:
            files = list(self.log_path.glob(f"*_{self.base_filename}.jsonl"))
        except Exception as e:
            logging.getLogger().warning(f"Falha ao listar logs em {self.log_path}: {e}")
            return

        for f in files:
            try:
                date_str = f.name.split("_")[0]
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if file_date < cutoff_date:
                    f.unlink()
            except ValueError:
                continue
            except Exception as e:
                logging.getLogger().warning(f"Falha ao remover log antigo {f}: {e}")

    # -------------------
    # Setup logging
    # -------------------
    def _setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Remove old handlers
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(pathname)s:%(lineno)d:%(funcName)s] %(message)s")
        )
        noise_filter = _DatabaseWorkerNoiseFilter(self)
        ch.addFilter(noise_filter)
        logger.addHandler(ch)
        self._console_handler = ch

        # Async JSON handler
        if self.file_enabled:
            qh = JsonQueueHandler(self.log_queue)
            qh.setLevel(logging.INFO)
            qh.addFilter(noise_filter)
            logger.addHandler(qh)
            self._file_handler = qh

        # Async batched database handler
        if self.db_enabled:
            dh = DatabaseQueueHandler(self)
            dh.setLevel(self.db_level)
            logger.addHandler(dh)
            self._db_handler = dh

    # -------------------
    # Global exception hooks
    # -------------------
    @staticmethod
    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger().error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    @staticmethod
    def _asyncio_exception_handler(loop, context):
        exception = context.get("exception")
        logger = logging.getLogger()
        if exception:
            logger.error("Unhandled asyncio exception", exc_info=(type(exception), exception, exception.__traceback__))
        else:
            logger.error("Unhandled asyncio error: %s", context.get("message"))

    # -------------------
    # Close logger
    # -------------------
    def close(self):
        if self._closed:
            return
        self._closed = True
        logging.getLogger().info("Logger closed")

        if self.file_enabled:
            self.stop_event.set()
            self.worker_thread.join(timeout=3)
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                try:
                    self._write(msg)
                except Exception as e:
                    print(f"[LoggerManager] Falha ao finalizar escrita de logs: {e}", file=sys.stderr)
                    break

        if self.db_enabled:
            self._db_stop_event.set()
            self._db_thread.join(timeout=10)
            if self._owns_db:
                self.db_manager.close()

        root = logging.getLogger()
        for handler in (self._file_handler, self._db_handler):
            if handler is not None:
                root.removeHandler(handler)
