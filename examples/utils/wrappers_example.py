import asyncio
from smartx_rfid.utils.wrappers import elapsed_time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


@elapsed_time
def example_sync():
    import time

    time.sleep(0.1)
    print("Exemplo sync")
    return "done-sync"


@elapsed_time
async def example_async():
    await asyncio.sleep(0.1)
    print("Exemplo async")
    return "done-async"


if __name__ == "__main__":
    example_sync()
    asyncio.run(example_async())
