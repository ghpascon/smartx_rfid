import logging
import os
import queue
import threading
import sys
import asyncio
from datetime import datetime, timezone


class LoggerManager:
    """
    Simple plug-and-play daily rotating logger.

    Usage:
        logger_manager = LoggerManager("logs", "myapp", max_days=7)
        logging.info("App started")
        # Exceptions, even uncaught, are automatically logged
    """

    def __init__(self, log_dir: str, base_filename: str, max_days: int = 7, use_utc: bool = False):
        self.log_dir = os.path.abspath(log_dir)
        self.base_filename = base_filename
        self.max_days = max_days
        self.use_utc = use_utc

        os.makedirs(self.log_dir, exist_ok=True)

        # Queue and thread for async logging
        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=10_000)
        self.stop_event = threading.Event()
        self.current_date = None
        self.filename = self._get_filename_for_date(self._now().date())

        self.worker_thread = threading.Thread(target=self._worker, name="LogWriterThread", daemon=True)
        self.worker_thread.start()

        # Setup logging
        self._setup_logging()

        # Global exception handlers
        sys.excepthook = self._handle_exception
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._asyncio_exception_handler)
        except RuntimeError:
            pass

        logging.info(f"Logger initialized: {self.filename}")

    # -------------------
    # Date & filename
    # -------------------
    def _now(self):
        return datetime.now(timezone.utc) if self.use_utc else datetime.now()

    def _get_filename_for_date(self, date: datetime.date):
        # Date before filename: YYYY-MM-DD_myapp.log
        return os.path.join(self.log_dir, f"{date:%Y-%m-%d}_{self.base_filename}.log")

    # -------------------
    # Worker
    # -------------------
    def _worker(self):
        while not self.stop_event.is_set() or not self.log_queue.empty():
            try:
                msg = self.log_queue.get(timeout=0.5)
                self._write(msg)
            except queue.Empty:
                continue

    def _write(self, msg: str):
        today = self._now().date()
        if today != self.current_date:
            self.current_date = today
            self.filename = self._get_filename_for_date(today)
            self._cleanup_old_logs()
        with open(self.filename, "a", encoding="utf-8", errors="replace") as f:
            f.write(msg)

    # -------------------
    # Cleanup old logs
    # -------------------
    def _cleanup_old_logs(self):
        files = []
        for f in os.listdir(self.log_dir):
            if f.endswith(".log") and f.startswith(f"{self.current_date:%Y-%m-%d}"):
                # skip current file
                continue
            if f.startswith("_".join([self.base_filename, ""])):  # ignore wrongly named files
                continue
            if f.endswith(".log"):
                try:
                    date_str = f.split("_")[0]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    files.append((file_date, os.path.join(self.log_dir, f)))
                except Exception:
                    continue
        files.sort(key=lambda x: x[0])
        for _, old_file in files[: -self.max_days]:
            try:
                os.remove(old_file)
            except Exception:
                pass

    # -------------------
    # Logging setup
    # -------------------
    def _setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Remove old handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Console
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(ch)

        # File (async)
        fh = logging.Handler()
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        fh.emit = self._enqueue
        logger.addHandler(fh)

    # -------------------
    # Enqueue log messages
    # -------------------
    def _enqueue(self, record: logging.LogRecord):
        try:
            # Include exception info if present
            msg = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s").format(record)
            if record.exc_info:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
            msg += "\n"
            self.log_queue.put_nowait(msg)
        except queue.Full:
            pass
        except Exception:
            self.handleError(record)

    # -------------------
    # Exception hooks
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
            logger.error("Unhandled asyncio exception", exc_info=exception)
        else:
            logger.error("Unhandled asyncio error: %s", context.get("message"))

    # -------------------
    # Close
    # -------------------
    def close(self):
        self.stop_event.set()
        self.worker_thread.join(timeout=3)
