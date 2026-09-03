import asyncio
import httpx

from smartx_rfid.webhook.xtrack import WebhookXtrack


def _make_dummy(posts):
    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None, timeout=None):
            posts.append({"url": url, "content": content, "headers": headers, "timeout": timeout})

            class DummyResponse:
                status_code = 200

            return DummyResponse()

    return DummyAsyncClient


def test_post_legacy_format(monkeypatch):
    posts = []
    Dummy = _make_dummy(posts)
    monkeypatch.setattr(httpx, "AsyncClient", Dummy)

    async def run():
        w = WebhookXtrack("http://example.com")
        await w.post({"device": "dev1", "ant": "2", "epc": "EPC123"})

    asyncio.run(run())

    assert len(posts) == 1
    assert "<command>ReportRead</command>" in posts[0]["content"]
    assert "TAGID=EPC123" in posts[0]["content"]


def test_add_to_queue_batch_size(monkeypatch):
    posts = []
    Dummy = _make_dummy(posts)
    monkeypatch.setattr(httpx, "AsyncClient", Dummy)

    async def run():
        w = WebhookXtrack("http://example.com", batch_size=3, batch_time=10, queue_limit=100)
        await w.add_to_queue({"device": "d1", "ant": "1", "epc": "E1"})
        await w.add_to_queue({"device": "d2", "ant": "2", "epc": "E2"})
        await w.add_to_queue({"device": "d3", "ant": "3", "epc": "E3"})

    asyncio.run(run())

    assert len(posts) == 1
    content = posts[0]["content"]
    assert "<command>ReportReadEx</command>" in content
    assert content.count("<data>") == 3
    assert "TAGID=E1" in content and "TAGID=E2" in content and "TAGID=E3" in content


def test_add_to_queue_batch_time(monkeypatch):
    posts = []
    Dummy = _make_dummy(posts)
    monkeypatch.setattr(httpx, "AsyncClient", Dummy)

    async def run():
        w = WebhookXtrack("http://example.com", batch_size=1000, batch_time=0.05, queue_limit=1000)
        await w.add_to_queue({"device": "d1", "ant": "1", "epc": "E1"})
        await w.add_to_queue({"device": "d2", "ant": "2", "epc": "E2"})
        await asyncio.sleep(0.1)

    asyncio.run(run())

    assert len(posts) == 1
    content = posts[0]["content"]
    assert content.count("<data>") == 2


def test_queue_limit_triggers_send(monkeypatch):
    posts = []
    Dummy = _make_dummy(posts)
    monkeypatch.setattr(httpx, "AsyncClient", Dummy)

    async def run():
        w = WebhookXtrack("http://example.com", batch_size=1000, batch_time=10, queue_limit=2)
        await w.add_to_queue({"device": "d1", "ant": "1", "epc": "E1"})
        await w.add_to_queue({"device": "d2", "ant": "2", "epc": "E2"})

    asyncio.run(run())

    assert len(posts) == 1


def test_missing_epc_is_skipped(monkeypatch):
    posts = []
    Dummy = _make_dummy(posts)
    monkeypatch.setattr(httpx, "AsyncClient", Dummy)

    async def run():
        w = WebhookXtrack("http://example.com", batch_size=3, batch_time=10, queue_limit=100)
        await w.add_to_queue({"device": "d1", "ant": "1", "epc": "E1"})
        await w.add_to_queue({"device": "d2", "ant": "2"})  # missing epc
        await w.add_to_queue({"device": "d3", "ant": "3", "epc": "E3"})

    asyncio.run(run())

    assert len(posts) == 1
    assert posts[0]["content"].count("<data>") == 2
    assert "TAGID=E1" in posts[0]["content"] and "TAGID=E3" in posts[0]["content"]
