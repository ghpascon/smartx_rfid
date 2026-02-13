import logging
import queue
import threading
import sys
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path


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
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "thread": record.threadName,
                "pathname": record.pathname,
            }
            # Include exception if present
            if record.exc_info:
                log_entry["exception"] = logging.Formatter().formatException(record.exc_info)

            # Include extra fields passed via 'extra' (not in standard LogRecord fields)
            standard_fields = set(
                [
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
                ]
            )
            for key, value in record.__dict__.items():
                if key not in standard_fields:
                    # Convert non-serializable objects to string
                    try:
                        json.dumps(value)
                        log_entry[key] = value
                    except TypeError:
                        log_entry[key] = str(value)

            self.log_queue.put_nowait(json.dumps(log_entry, ensure_ascii=False))
        except queue.Full:
            # Could implement drop counter here
            pass
        except Exception:
            self.handleError(record)

    def handleError(self, record):
        # Log error to console (default behavior)
        super().handleError(record)
        # Also log error to JSON file
        try:
            error_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
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


class LoggerManager:
    """
    Professional logger with daily rotation, JSON file output, console output,
    automatic cleanup of old logs, and async logging via queue.
    """

    def __init__(self, log_path: str, base_filename: str, storage_days: int = 7):
        self.base_filename = base_filename
        self.storage_days = storage_days

        # Ensure log directory exists
        self.log_path = Path(log_path).resolve()
        self.log_path.mkdir(parents=True, exist_ok=True)

        # Queue + worker thread for async logging
        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=10_000)
        self.stop_event = threading.Event()
        self.current_date = datetime.now(timezone.utc).date()
        self.filename = self._get_filename_for_date(self.current_date)

        self.worker_thread = threading.Thread(target=self._worker, name="LogWriterThread", daemon=True)
        self.worker_thread.start()

        # Setup logging
        self._setup_logging()

        # Global exception hooks
        sys.excepthook = self._handle_exception
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._asyncio_exception_handler)
        except RuntimeError:
            pass

        logging.getLogger().info(f"Logger initialized: {self.filename}")

    # -------------------
    # Filename helpers
    # -------------------
    def _get_filename_for_date(self, date: datetime.date) -> str:
        return str(self.log_path / f"{date:%Y-%m-%d}_{self.base_filename}.json")

    # -------------------
    # Worker for async writing
    # -------------------
    def _worker(self):
        while not self.stop_event.is_set() or not self.log_queue.empty():
            try:
                msg = self.log_queue.get(timeout=0.5)
                self._write(msg)
            except queue.Empty:
                continue

    def _write(self, msg: str):
        today = datetime.now(timezone.utc).date()
        if today != self.current_date:
            self.current_date = today
            self.filename = self._get_filename_for_date(today)
            self._cleanup_old_logs()
        with open(self.filename, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    # -------------------
    # Cleanup old logs
    # -------------------
    def _cleanup_old_logs(self):
        logs = []
        for f in self.log_path.glob(f"*_{self.base_filename}.json"):
            try:
                date_str = f.name.split("_")[0]
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                logs.append((file_date, f))
            except Exception:
                continue
        logs.sort(key=lambda x: x[0])
        for old_date, old_file in logs[: -self.storage_days]:
            try:
                old_file.unlink()
            except Exception:
                pass

    # -------------------
    # Setup logging
    # -------------------
    def _setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # Remove old handlers
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(pathname)s:%(lineno)d:%(funcName)s] %(message)s")
        )
        logger.addHandler(ch)

        # Async JSON file handler
        qh = JsonQueueHandler(self.log_queue)
        qh.setLevel(logging.DEBUG)
        logger.addHandler(qh)

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
        self.stop_event.set()
        self.worker_thread.join(timeout=3)
        # Flush remaining messages
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._write(msg)
        logging.getLogger().info("Logger closed")
