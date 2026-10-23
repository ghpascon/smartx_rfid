import asyncio
import json
import time

import pytest

from smartx_rfid.dispatcher.main import EventDispatcher, HttpDispatcher, MongoDispatcher, MqttDispatcher, SqlDispatcher


def _write_dispatch(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


class _DummyHttpClient:
    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_mongodb_dispatch_uses_placeholders_and_respects_flush_interval(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mongo_tag.json",
        {
            "dispatch_type": "mongodb",
            "on_event": "tag",
            "connection_string": "mongodb://localhost:27017",
            "database": "smartx",
            "collection": "events",
            "ordered": True,
            "allow_batches": True,
            "batch_size": 100,
            "flush_interval_seconds": 0.30,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.05,
            "document": {
                "device": "{name}",
                "device_serial_number": "{device[serial_number]}",
                "event": "{event_type}",
                "epc": "{data[epc]}",
                "rssi": "{data[rssi]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    mongo = MongoDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt, mongo=mongo)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    captured = {}

    async def fake_insert_many_once(key, docs, log_ctx):
        captured["called_at"] = time.monotonic()
        captured["key"] = key
        captured["docs"] = docs
        captured["log_ctx"] = log_ctx
        sent.set()

    monkeypatch.setattr(mongo, "_insert_many_once", fake_insert_many_once)

    await dispatcher.start()
    try:
        start = time.monotonic()
        device = {"name": "XPAD", "serial_number": "SN-XPAD"}
        await dispatcher.add_async(device, "tag", {"epc": "E1", "rssi": -55})
        await dispatcher.add_async(device, "tag", {"epc": "E2", "rssi": -57})
        await dispatcher.add_async(device, "tag", {"epc": "E3", "rssi": -58})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        elapsed = captured["called_at"] - start
        assert elapsed >= 0.25
        assert captured["key"].database == "smartx"
        assert captured["key"].collection == "events"
        assert isinstance(captured["docs"], list)
        assert len(captured["docs"]) == 3
        assert captured["docs"][0]["device"] == "XPAD"
        assert captured["docs"][0]["device_serial_number"] == "SN-XPAD"
        assert captured["docs"][0]["event"] == "tag"
        assert captured["docs"][0]["epc"] == "E1"
        assert captured["docs"][0]["rssi"] == -55
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_mongodb_dispatch_uses_batch_size_from_json(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mongo_batch_size.json",
        {
            "dispatch_type": "mongodb",
            "on_event": "tag",
            "connection_string": "mongodb://localhost:27017",
            "database": "smartx",
            "collection": "events",
            "allow_batches": True,
            "batch_size": 2,
            "flush_interval_seconds": 5.0,
            "document": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    mongo = MongoDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt, mongo=mongo)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    docs_list = []

    async def fake_insert_many_once(key, docs, log_ctx):
        docs_list.append(docs)
        sent.set()

    monkeypatch.setattr(mongo, "_insert_many_once", fake_insert_many_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2"})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        assert len(docs_list) == 1
        assert isinstance(docs_list[0], list)
        assert len(docs_list[0]) == 2
        assert docs_list[0][0]["epc"] == "E1"
        assert docs_list[0][1]["epc"] == "E2"
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_mongodb_dispatch_can_disable_batches_with_json_allow_batches(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mongo_allow_false.json",
        {
            "dispatch_type": "mongodb",
            "on_event": "tag",
            "connection_string": "mongodb://localhost:27017",
            "database": "smartx",
            "collection": "events",
            "allow_batches": False,
            "batch_size": 100,
            "flush_interval_seconds": 5.0,
            "document": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    mongo = MongoDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt, mongo=mongo)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    calls = []

    async def fake_insert_many_once(key, docs, log_ctx):
        calls.append(docs)
        if len(calls) >= 2:
            sent.set()

    monkeypatch.setattr(mongo, "_insert_many_once", fake_insert_many_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2"})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        assert len(calls) == 2
        assert len(calls[0]) == 1
        assert len(calls[1]) == 1
        assert calls[0][0]["epc"] == "E1"
        assert calls[1][0]["epc"] == "E2"
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_invalid_mongodb_ordered_is_rejected_on_reload(tmp_path):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "invalid_mongo.json",
        {
            "dispatch_type": "mongodb",
            "on_event": "tag",
            "connection_string": "mongodb://localhost:27017",
            "database": "smartx",
            "collection": "events",
            "ordered": "yes",
            "document": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    mongo = MongoDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt, mongo=mongo)
    http._client = _DummyHttpClient()

    await dispatcher.start()
    try:
        stats = dispatcher.get_stats()
        assert stats["dispatches_loaded"] == 0
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_mongodb_dispatch_retries_before_success(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mongo_retry.json",
        {
            "dispatch_type": "mongodb",
            "on_event": "tag",
            "connection_string": "mongodb://localhost:27017",
            "database": "smartx",
            "collection": "events",
            "allow_batches": False,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.01,
            "document": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    mongo = MongoDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt, mongo=mongo)
    http._client = _DummyHttpClient()

    done = asyncio.Event()
    attempts = {"count": 0}

    async def flaky_insert_many_once(key, docs, log_ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("simulated timeout")
        done.set()

    monkeypatch.setattr(mongo, "_insert_many_once", flaky_insert_many_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await asyncio.wait_for(done.wait(), timeout=2.0)
        assert attempts["count"] == 2
    finally:
        await dispatcher.stop()
