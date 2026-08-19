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
            standard_fields = {
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
            }

            for key, value in record.__dict__.items():
                if key not in standard_fields:
                    try:
                        json.dumps(value)
                        log_entry[key] = value
                    except TypeError:
                        log_entry[key] = str(value)

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


class LoggerManager:
    """
    Professional logger with daily rotation, JSONL file output, console output,
    automatic cleanup of old logs, and async logging via queue.
    """

    def __init__(self, log_path: str, base_filename: str, storage_days: int = 7):
        self.base_filename = base_filename
        self.storage_days = storage_days
        self.current_date = datetime.now(timezone.utc).astimezone().date()

        requested_path = Path(log_path).expanduser().resolve()
        self.default_log_path = (Path.cwd() / "logs").resolve()
        self.log_path = self._resolve_writable_log_path(requested_path)

        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=10_000)
        self.stop_event = threading.Event()
        self.filename = self._get_filename_for_date(self.current_date)

        self.worker_thread = threading.Thread(target=self._worker, name="LogWriterThread", daemon=True)
        self.worker_thread.start()

        self._setup_logging()
        self._cleanup_old_logs()  # Cleanup inicial seguro

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
        return str(self.log_path / f"{date:%Y-%m-%d}_{self.base_filename}.jsonl")

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
        while not self.stop_event.is_set() or not self.log_queue.empty():
            try:
                msg = self.log_queue.get(timeout=0.5)
                try:
                    self._write(msg)
                except Exception as e:
                    logging.getLogger().error("Erro ao escrever log", exc_info=e)
            except queue.Empty:
                continue

    def _write(self, msg: str):
        today = datetime.now(timezone.utc).astimezone().date()
        if today != self.current_date:
            self.current_date = today
            self.filename = self._get_filename_for_date(today)
            self._cleanup_old_logs()
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
        if self.storage_days <= 0:
            return

        logs = []
        try:
            files = list(self.log_path.glob(f"*_{self.base_filename}.jsonl"))
        except Exception as e:
            logging.getLogger().warning(f"Falha ao listar logs em {self.log_path}: {e}")
            return

        for f in files:
            try:
                date_str = f.name.split("_")[0]
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                logs.append((file_date, f))
            except ValueError:
                continue

        logs.sort(key=lambda x: x[0])
        excess_logs = len(logs) - self.storage_days
        if excess_logs <= 0:
            return

        for _, old_file in logs[:excess_logs]:
            try:
                old_file.unlink()
            except Exception as e:
                logging.getLogger().warning(f"Falha ao remover log antigo {old_file}: {e}")

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
        logger.addHandler(ch)

        # Async JSON handler
        qh = JsonQueueHandler(self.log_queue)
        qh.setLevel(logging.INFO)
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
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            try:
                self._write(msg)
            except Exception as e:
                print(f"[LoggerManager] Falha ao finalizar escrita de logs: {e}", file=sys.stderr)
                break
        logging.getLogger().info("Logger closed")
