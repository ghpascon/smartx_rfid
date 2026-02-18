import asyncio
from smartx_rfid.utils.wrappers import elapsed_time


@elapsed_time
def test_sync():
    import time

    time.sleep(0.2)
    return "ok-sync"


@elapsed_time
async def test_async():
    await asyncio.sleep(0.2)
    return "ok-async"


def test_all():
    assert test_sync() == "ok-sync"
    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(test_async()) == "ok-async"
