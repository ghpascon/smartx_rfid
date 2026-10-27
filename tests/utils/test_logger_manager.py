import json
import logging
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import DeclarativeBase

from smartx_rfid.db import DatabaseManager
from smartx_rfid.db._main import DatabaseOperationError
from smartx_rfid.models.log import Logs
from smartx_rfid.utils import LoggerManager


class CustomBase(DeclarativeBase):
    pass


class CustomLog(CustomBase):
    __tablename__ = "custom_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    level = Column(String(5), nullable=False)
    message = Column(String(20), nullable=False)


def _transient_error() -> DatabaseOperationError:
    return DatabaseOperationError("down", sa_exc.OperationalError("INSERT", {}, Exception("connection refused")))


def _data_error() -> DatabaseOperationError:
    return DatabaseOperationError("bad", sa_exc.IntegrityError("INSERT", {}, Exception("constraint failed")))


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    handlers, level, excepthook = root.handlers[:], root.level, sys.excepthook
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    sys.excepthook = excepthook


@pytest.fixture
def create_logger():
    created = []

    def factory(**kwargs):
        kwargs.setdefault("db_flush_interval", 0.1)
        manager = LoggerManager(**kwargs)
        created.append(manager)
        return manager

    yield factory
    for manager in created:
        manager.close()


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'logs.db'}"


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _db_messages(manager, model=Logs):
    return [row.message for row in manager.db_manager.get_all(model)]


# -------------------
# Filesystem (compatibility)
# -------------------
def test_file_only_writes_jsonl(create_logger, tmp_path):
    manager = create_logger(log_path=str(tmp_path), base_filename="app", storage_days=1)
    assert manager.file_enabled and not manager.db_enabled

    logging.info("hello file", extra={"device": "R700"})
    manager.close()

    entries = _read_jsonl(tmp_path.joinpath(manager.filename))
    assert any(e["message"] == "hello file" and e["device"] == "R700" for e in entries)


def test_positional_storage_days_is_kept(create_logger, tmp_path):
    manager = create_logger(log_path=str(tmp_path), base_filename="app", storage_days=3)
    assert manager.storage_days == 3


def test_file_retention_cleanup_runs_at_startup(create_logger, tmp_path):
    old_log = tmp_path / "2020-01-01_app.jsonl"
    recent_log = tmp_path / "2026-10-26_app.jsonl"
    old_log.touch()
    recent_log.touch()

    create_logger(log_path=str(tmp_path), base_filename="app", storage_days=1)

    assert not old_log.exists()
    assert recent_log.exists()


def test_default_base_filename_uses_executed_script(create_logger, tmp_path, monkeypatch):
    class FakeMain:
        __file__ = "/some/where/my_script.py"

    monkeypatch.setitem(sys.modules, "__main__", FakeMain)
    manager = create_logger(log_path=str(tmp_path))
    assert manager.base_filename == "my_script"
    assert manager.filename.endswith("_my_script.jsonl")


def test_default_base_filename_for_dunder_main(create_logger, tmp_path, monkeypatch):
    pkg = tmp_path / "mypkg"
    pkg.mkdir()

    class FakeMain:
        __file__ = str(pkg / "__main__.py")

    monkeypatch.setitem(sys.modules, "__main__", FakeMain)
    assert LoggerManager._detect_script_name() == "mypkg"


def test_no_destination_defaults_to_file(create_logger, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manager = create_logger(base_filename="app")
    assert manager.file_enabled
    assert manager.log_path == (tmp_path / "logs").resolve()


# -------------------
# Database
# -------------------
def test_database_only_inserts_rows(create_logger, db_url):
    manager = create_logger(database_url=db_url)
    assert manager.db_enabled and not manager.file_enabled
    assert manager.wait_until_ready()

    logging.info("hello db", extra={"device": "R700", "count": 3})
    assert manager.flush()

    rows = manager.db_manager.get_all(Logs)
    row = next(r for r in rows if r.message == "hello db")
    assert row.level == "INFO"
    assert row.function == "test_database_only_inserts_rows"
    assert row.line and row.pathname.endswith("test_logger_manager.py")
    assert json.loads(row.extra) == {"device": "R700", "count": 3}
    assert row.exception is None
    assert row.timestamp is not None


def test_database_stores_exception(create_logger, db_url):
    manager = create_logger(database_url=db_url)
    try:
        raise ValueError("boom")
    except ValueError as exc:
        logging.error("failed", exc_info=exc)
    assert manager.flush()

    row = next(r for r in manager.db_manager.get_all(Logs) if r.message == "failed")
    assert row.level == "ERROR"
    assert "ValueError: boom" in row.exception


def test_file_and_database_together(create_logger, tmp_path, db_url):
    manager = create_logger(log_path=str(tmp_path), base_filename="both", database_url=db_url)
    assert manager.file_enabled and manager.db_enabled

    logging.info("to both")
    assert manager.flush()
    manager.close()

    assert any(e["message"] == "to both" for e in _read_jsonl(tmp_path.joinpath(manager.filename)))
    reopened = DatabaseManager(db_url)
    reopened.initialize()
    assert "to both" in [r.message for r in reopened.get_all(Logs)]
    reopened.close()


def test_db_level_filters_rows(create_logger, db_url):
    manager = create_logger(database_url=db_url, db_level=logging.WARNING)
    logging.info("too low")
    logging.warning("kept")
    assert manager.flush()
    messages = _db_messages(manager)
    assert "kept" in messages and "too low" not in messages


def test_logs_are_batched(create_logger, db_url, monkeypatch):
    manager = create_logger(database_url=db_url, db_batch_size=50, db_flush_interval=0.2)
    assert manager.wait_until_ready()

    calls = []
    original = manager.db_manager.bulk_insert

    def spy(model, data, session=None):
        calls.append(len(data))
        return original(model, data, session=session)

    monkeypatch.setattr(manager.db_manager, "bulk_insert", spy)

    for i in range(200):
        logging.info(f"msg {i}")
    assert manager.flush()

    assert sum(calls) >= 200
    assert len(calls) < 100  # far fewer round trips than rows
    assert max(calls) <= 50


def test_close_flushes_pending_rows(create_logger, db_url):
    manager = create_logger(database_url=db_url, db_flush_interval=60)
    assert manager.wait_until_ready()
    for i in range(5):
        logging.info(f"pending {i}")
    manager.close()

    reopened = DatabaseManager(db_url)
    reopened.initialize()
    messages = [r.message for r in reopened.get_all(Logs)]
    reopened.close()
    assert [m for m in messages if m.startswith("pending")] == [f"pending {i}" for i in range(5)]


def test_worker_own_logs_are_not_persisted(create_logger, db_url):
    manager = create_logger(database_url=db_url)
    assert manager.wait_until_ready()
    logging.info("only me")
    assert manager.flush()
    messages = _db_messages(manager)
    assert not any("Bulk inserted" in m or "Tables created" in m for m in messages)


def test_custom_model_only_fills_existing_columns_and_truncates(create_logger, db_url):
    manager = create_logger(database_url=db_url, database_model=CustomLog)
    assert manager.wait_until_ready()

    logging.info("x" * 100)
    assert manager.flush()

    rows = manager.db_manager.get_all(CustomLog)
    row = next(r for r in rows if r.message.startswith("x"))
    assert row.message == "x" * 20
    assert row.level == "INFO"


def test_external_database_manager_is_not_closed(create_logger, db_url):
    db = DatabaseManager(db_url)
    manager = create_logger(database_manager=db)
    assert manager.wait_until_ready()
    logging.info("external")
    assert manager.flush()
    manager.close()

    assert db.get_connection_info()["status"] == "connected"
    assert "external" in [r.message for r in db.get_all(Logs)]
    db.close()


def test_owned_database_manager_is_closed(create_logger, db_url):
    manager = create_logger(database_url=db_url)
    db = manager.db_manager
    manager.close()
    assert db.get_connection_info()["status"] == "not_initialized"


def test_database_retention_deletes_old_rows(create_logger, db_url):
    db = DatabaseManager(db_url)
    db.initialize()
    db.register_models(Logs)
    db.create_tables()
    old = datetime.now().astimezone() - timedelta(days=30)
    db.insert_record(Logs, {"timestamp": old, "level": "INFO", "message": "ancient"})

    manager = create_logger(database_manager=db, db_storage_days=7)
    assert manager.wait_until_ready()
    logging.info("fresh")
    assert manager.flush()

    messages = [r.message for r in db.get_all(Logs)]
    assert "ancient" not in messages and "fresh" in messages
    manager.close()
    db.close()


def test_database_retention_defaults_to_file_storage_days(create_logger, db_url):
    manager = create_logger(database_url=db_url, storage_days=3)
    assert manager.db_storage_days == 3


def test_zero_database_retention_keeps_only_today(create_logger, db_url):
    db = DatabaseManager(db_url)
    db.initialize()
    db.register_models(Logs)
    db.create_tables()
    yesterday = datetime.now().astimezone() - timedelta(days=1)
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    db.insert_record(Logs, {"timestamp": yesterday, "level": "INFO", "message": "yesterday"})
    db.insert_record(Logs, {"timestamp": today, "level": "INFO", "message": "today"})

    manager = create_logger(database_manager=db, db_storage_days=0)
    assert manager.wait_until_ready()

    messages = [row.message for row in db.get_all(Logs)]
    assert "yesterday" not in messages and "today" in messages
    manager.close()
    db.close()


# -------------------
# Resilience
# -------------------
def test_never_blocks_when_database_is_stuck(create_logger, db_url, monkeypatch):
    manager = create_logger(database_url=db_url, db_queue_size=10, db_batch_size=5)
    assert manager.wait_until_ready()

    release = threading.Event()
    monkeypatch.setattr(manager.db_manager, "bulk_insert", lambda *a, **k: release.wait(5))

    start = time.monotonic()
    for i in range(2000):
        logging.info(f"flood {i}")
    elapsed = time.monotonic() - start
    release.set()

    assert elapsed < 2.0
    assert manager.get_stats()["db_dropped"] > 0


def test_retries_while_database_is_down(create_logger, db_url, monkeypatch):
    manager = create_logger(database_url=db_url)
    assert manager.wait_until_ready()

    original = manager.db_manager.bulk_insert
    state = {"calls": 0}

    def flaky(model, data, session=None):
        state["calls"] += 1
        if state["calls"] <= 2:
            raise _transient_error()
        return original(model, data, session=session)

    monkeypatch.setattr(manager.db_manager, "bulk_insert", flaky)

    logging.info("survives outage")
    assert manager.flush(timeout=10)

    assert state["calls"] >= 3
    assert "survives outage" in _db_messages(manager)
    assert manager.get_stats()["db_failures"] >= 2


def test_poison_row_does_not_block_others(create_logger, db_url, monkeypatch):
    manager = create_logger(database_url=db_url, db_flush_interval=0.3)
    assert manager.wait_until_ready()

    original = manager.db_manager.bulk_insert

    def picky(model, data, session=None):
        if any(row["message"] == "poison" for row in data):
            raise _data_error()
        return original(model, data, session=session)

    monkeypatch.setattr(manager.db_manager, "bulk_insert", picky)

    logging.info("good 1")
    logging.info("poison")
    logging.info("good 2")
    assert manager.flush()

    messages = _db_messages(manager)
    assert "good 1" in messages and "good 2" in messages and "poison" not in messages
    assert manager.get_stats()["db_dropped"] == 1


def test_database_unavailable_at_startup_recovers(create_logger, db_url, monkeypatch):
    db = DatabaseManager(db_url)
    db.initialize()
    original_create = db.create_tables
    state = {"calls": 0}

    def flaky_create(checkfirst=True):
        state["calls"] += 1
        if state["calls"] == 1:
            raise _transient_error()
        return original_create(checkfirst=checkfirst)

    monkeypatch.setattr(db, "create_tables", flaky_create)

    manager = create_logger(database_manager=db)  # must not raise nor block
    logging.info("queued before ready")
    assert manager.wait_until_ready(timeout=10)
    assert manager.flush(timeout=10)
    assert "queued before ready" in _db_messages(manager)
    db.close()


def test_close_with_database_down_does_not_hang(create_logger, db_url, monkeypatch):
    manager = create_logger(database_url=db_url, db_flush_interval=60)
    assert manager.wait_until_ready()
    monkeypatch.setattr(manager.db_manager, "bulk_insert", lambda *a, **k: (_ for _ in ()).throw(_transient_error()))

    logging.info("lost")
    start = time.monotonic()
    manager.close()
    assert time.monotonic() - start < 5
    assert manager.get_stats()["db_dropped"] >= 1


# -------------------
# Validation
# -------------------
def test_url_and_manager_are_mutually_exclusive(db_url):
    with pytest.raises(ValueError):
        LoggerManager(database_url=db_url, database_manager=DatabaseManager(db_url))


def test_invalid_model_is_rejected(db_url):
    class NotAModel:
        pass

    with pytest.raises(ValueError):
        LoggerManager(database_url=db_url, database_model=NotAModel)


@pytest.mark.parametrize("kwargs", [{"db_batch_size": 0}, {"db_queue_size": 0}, {"db_flush_interval": 0}])
def test_invalid_db_settings_are_rejected(db_url, kwargs):
    with pytest.raises(ValueError):
        LoggerManager(database_url=db_url, **kwargs)
