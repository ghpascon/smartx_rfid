import asyncio
import json
import time

import pytest

from smartx_rfid.dispatcher.main import EventDispatcher, HttpDispatcher, SqlDispatcher


def _write_dispatch(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


class _DummyClient:
    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_post_dispatch_uses_placeholders_and_respects_flush_interval(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "post_tag.json",
        {
            "dispatch_type": "post",
            "on_event": "tag",
            "url": "http://localhost:5001",
            "allow_batches": True,
            "batch_size": 100,
            "flush_interval_seconds": 0.30,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.05,
            "headers": {"Content-Type": "application/json"},
            "body": {
                "device": "{name}",
                "event": "{event_type}",
                "epc": "{data[epc]}",
                "rssi": "{data[rssi]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql)
    http._client = _DummyClient()

    sent = asyncio.Event()
    captured = {}

    async def fake_post_once(url, headers, payload, log_ctx):
        captured["called_at"] = time.monotonic()
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["log_ctx"] = log_ctx
        sent.set()

    monkeypatch.setattr(http, "_post_once", fake_post_once)

    await dispatcher.start()
    try:
        start = time.monotonic()
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1", "rssi": -55})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2", "rssi": -57})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E3", "rssi": -58})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        elapsed = captured["called_at"] - start
        assert elapsed >= 0.25
        assert captured["url"] == "http://localhost:5001"
        assert isinstance(captured["payload"], list)
        assert len(captured["payload"]) == 3
        assert captured["payload"][0]["device"] == "XPAD"
        assert captured["payload"][0]["event"] == "tag"
        assert captured["payload"][0]["epc"] == "E1"
        assert captured["payload"][0]["rssi"] == -55
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_sql_dispatch_uses_placeholders_and_respects_flush_interval(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    db_path = tmp_path / "events.db"
    _write_dispatch(
        dispatches_dir / "sql_tag.json",
        {
            "dispatch_type": "sql",
            "on_event": "tag",
            "allow_batches": True,
            "batch_size": 100,
            "connection_string": f"sqlite+aiosqlite:///{db_path}",
            "query": "INSERT INTO events (device, epc, rssi) VALUES (:device, :epc, :rssi)",
            "flush_interval_seconds": 0.30,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.05,
            "params": {
                "device": "{name}",
                "epc": "{data[epc]}",
                "rssi": "{data[rssi]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql)
    http._client = _DummyClient()

    executed = asyncio.Event()
    captured = {}

    async def fake_execute_many(connection_string, query, params_list):
        captured["called_at"] = time.monotonic()
        captured["connection_string"] = connection_string
        captured["query"] = query
        captured["params_list"] = params_list
        executed.set()

    monkeypatch.setattr(sql, "_execute_many", fake_execute_many)

    await dispatcher.start()
    try:
        start = time.monotonic()
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1", "rssi": -55})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2", "rssi": -60})

        await asyncio.wait_for(executed.wait(), timeout=2.0)

        elapsed = captured["called_at"] - start
        assert elapsed >= 0.25
        assert captured["query"].startswith("INSERT INTO events")
        assert captured["connection_string"].startswith("sqlite+aiosqlite:///")
        assert len(captured["params_list"]) == 2
        assert captured["params_list"][0]["device"] == "XPAD"
        assert captured["params_list"][0]["epc"] == "E1"
        assert captured["params_list"][0]["rssi"] == -55
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_post_dispatch_uses_batch_size_from_json(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "post_batch_size.json",
        {
            "dispatch_type": "post",
            "on_event": "tag",
            "url": "http://localhost:5001",
            "allow_batches": True,
            "batch_size": 2,
            "flush_interval_seconds": 5.0,
            "body": {
                "epc": "{data[epc]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql)
    http._client = _DummyClient()

    sent = asyncio.Event()
    payloads = []

    async def fake_post_once(url, headers, payload, log_ctx):
        payloads.append(payload)
        sent.set()

    monkeypatch.setattr(http, "_post_once", fake_post_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2"})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        assert len(payloads) == 1
        assert isinstance(payloads[0], list)
        assert len(payloads[0]) == 2
        assert payloads[0][0]["epc"] == "E1"
        assert payloads[0][1]["epc"] == "E2"
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_sql_dispatch_can_disable_batches_with_json_allow_batches(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    db_path = tmp_path / "events.db"
    _write_dispatch(
        dispatches_dir / "sql_allow_false.json",
        {
            "dispatch_type": "sql",
            "on_event": "tag",
            "allow_batches": False,
            "batch_size": 100,
            "connection_string": f"sqlite+aiosqlite:///{db_path}",
            "query": "INSERT INTO events (device, epc) VALUES (:device, :epc)",
            "flush_interval_seconds": 5.0,
            "params": {
                "device": "{name}",
                "epc": "{data[epc]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql)
    http._client = _DummyClient()

    executed = asyncio.Event()
    batches = []

    async def fake_execute_many(connection_string, query, params_list):
        batches.append(params_list)
        if len(batches) >= 2:
            executed.set()

    monkeypatch.setattr(sql, "_execute_many", fake_execute_many)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2"})

        await asyncio.wait_for(executed.wait(), timeout=2.0)

        assert len(batches) == 2
        assert len(batches[0]) == 1
        assert len(batches[1]) == 1
        assert batches[0][0]["epc"] == "E1"
        assert batches[1][0]["epc"] == "E2"
    finally:
        await dispatcher.stop()
