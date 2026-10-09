import asyncio
import json
import time

import pytest

from smartx_rfid.dispatcher.main import EventDispatcher, HttpDispatcher, MqttDispatcher, SqlDispatcher


def _write_dispatch(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


class _DummyHttpClient:
    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_mqtt_dispatch_uses_placeholders_and_respects_flush_interval(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mqtt_tag.json",
        {
            "dispatch_type": "mqtt",
            "on_event": "tag",
            "host": "localhost",
            "port": 1883,
            "topic": "smartx/{name}/{event_type}",
            "qos": 1,
            "retain": False,
            "allow_batches": True,
            "batch_size": 100,
            "flush_interval_seconds": 0.30,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.05,
            "payload": {
                "device": "{name}",
                "event": "{event_type}",
                "epc": "{data[epc]}",
                "rssi": "{data[rssi]}",
            },
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    captured = {}

    async def fake_publish_once(key, payload, log_ctx):
        captured["called_at"] = time.monotonic()
        captured["key"] = key
        captured["payload"] = payload
        captured["log_ctx"] = log_ctx
        sent.set()

    monkeypatch.setattr(mqtt, "_publish_once", fake_publish_once)

    await dispatcher.start()
    try:
        start = time.monotonic()
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1", "rssi": -55})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2", "rssi": -57})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E3", "rssi": -58})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        elapsed = captured["called_at"] - start
        assert elapsed >= 0.25
        assert captured["key"].host == "localhost"
        assert captured["key"].topic == "smartx/XPAD/tag"
        assert isinstance(captured["payload"], list)
        assert len(captured["payload"]) == 3
        assert captured["payload"][0]["device"] == "XPAD"
        assert captured["payload"][0]["event"] == "tag"
        assert captured["payload"][0]["epc"] == "E1"
        assert captured["payload"][0]["rssi"] == -55
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_mqtt_dispatch_uses_batch_size_from_json(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mqtt_batch_size.json",
        {
            "dispatch_type": "mqtt",
            "on_event": "tag",
            "host": "localhost",
            "topic": "smartx/batch",
            "allow_batches": True,
            "batch_size": 2,
            "flush_interval_seconds": 5.0,
            "payload": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    payloads = []

    async def fake_publish_once(key, payload, log_ctx):
        payloads.append(payload)
        sent.set()

    monkeypatch.setattr(mqtt, "_publish_once", fake_publish_once)

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
async def test_mqtt_dispatch_can_disable_batches_with_json_allow_batches(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mqtt_allow_false.json",
        {
            "dispatch_type": "mqtt",
            "on_event": "tag",
            "host": "localhost",
            "topic": "smartx/single",
            "allow_batches": False,
            "batch_size": 100,
            "flush_interval_seconds": 5.0,
            "payload": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt)
    http._client = _DummyHttpClient()

    sent = asyncio.Event()
    payloads = []

    async def fake_publish_once(key, payload, log_ctx):
        payloads.append(payload)
        if len(payloads) >= 2:
            sent.set()

    monkeypatch.setattr(mqtt, "_publish_once", fake_publish_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await dispatcher.add_async("XPAD", "tag", {"epc": "E2"})

        await asyncio.wait_for(sent.wait(), timeout=2.0)

        assert len(payloads) == 2
        assert isinstance(payloads[0], dict)
        assert isinstance(payloads[1], dict)
        assert payloads[0]["epc"] == "E1"
        assert payloads[1]["epc"] == "E2"
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_invalid_mqtt_qos_is_rejected_on_reload(tmp_path):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "invalid_mqtt.json",
        {
            "dispatch_type": "mqtt",
            "on_event": "tag",
            "host": "localhost",
            "topic": "smartx/invalid",
            "qos": 7,
            "payload": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt)
    http._client = _DummyHttpClient()

    await dispatcher.start()
    try:
        stats = dispatcher.get_stats()
        assert stats["dispatches_loaded"] == 0
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_mqtt_dispatch_retries_before_success(tmp_path, monkeypatch):
    dispatches_dir = tmp_path / "dispatches"
    dispatches_dir.mkdir()

    _write_dispatch(
        dispatches_dir / "mqtt_retry.json",
        {
            "dispatch_type": "mqtt",
            "on_event": "tag",
            "host": "localhost",
            "topic": "smartx/retry",
            "allow_batches": False,
            "retry_attempts": 2,
            "retry_backoff_seconds": 0.01,
            "payload": {"epc": "{data[epc]}"},
        },
    )

    http = HttpDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    sql = SqlDispatcher(batch_size=1000, flush_interval_seconds=0.05)
    mqtt = MqttDispatcher(batch_size=1000, flush_interval_seconds=0.05, sender_workers=1)
    dispatcher = EventDispatcher(dispatches_path=str(dispatches_dir), http=http, sql=sql, mqtt=mqtt)
    http._client = _DummyHttpClient()

    published = asyncio.Event()
    attempts = {"count": 0}

    async def flaky_publish_once(key, payload, log_ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("simulated timeout")
        published.set()

    monkeypatch.setattr(mqtt, "_publish_once", flaky_publish_once)

    await dispatcher.start()
    try:
        await dispatcher.add_async("XPAD", "tag", {"epc": "E1"})
        await asyncio.wait_for(published.wait(), timeout=2.0)
        assert attempts["count"] == 2
    finally:
        await dispatcher.stop()
