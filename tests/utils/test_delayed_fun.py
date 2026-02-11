import pytest
from src.smartx_rfid.utils.functions import delayed_function


@pytest.mark.asyncio
async def test_delayed_function_with_sync_func():
    calls = []

    def sync_func(x, y=0):
        calls.append((x, y))
        return x + y

    result = await delayed_function(sync_func, 0.1, 2, y=3)
    assert result == 5
    assert calls == [(2, 3)]


@pytest.mark.asyncio
async def test_delayed_function_with_async_func():
    calls = []

    async def async_func(x, y=0):
        calls.append((x, y))
        return x * y

    result = await delayed_function(async_func, 0.1, 4, y=5)
    assert result == 20
    assert calls == [(4, 5)]


@pytest.mark.asyncio
async def test_delayed_function_delay():
    import time

    def sync_func():
        return "done"

    start = time.monotonic()
    await delayed_function(sync_func, 0.2)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.18  # allow some tolerance
