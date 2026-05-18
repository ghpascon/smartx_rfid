# Imports essenciais
import asyncio
import random
import time
from smartx_rfid.dispatcher import EventDispatcher

# Constantes
EVENT_QTY = 1000
PRODUCER_WORKERS = 10


def build_epc(index: int) -> str:
    return f"{index:024X}"


def build_tid_from_epc(epc: str) -> str:
    return f"E280{epc[4:]}"


async def produce_events(dispatcher: EventDispatcher, start_index: int, end_index: int, seed: int) -> int:
    rng = random.Random(seed)
    for index in range(start_index, end_index):
        epc = build_epc(index)
        tid = build_tid_from_epc(epc)
        device = "XPAD" if rng.randint(0, 1) == 0 else "R700"
        ant = rng.randint(1, 4)
        await dispatcher.add_async(
            device,
            "tag",
            {
                "epc": epc,
                "tid": tid,
                "ant": ant,
                "rssi": -50,
            },
        )
    return end_index - start_index


async def main():
    dispatcher = EventDispatcher(
        dispatches_path="examples/dispatcher/dispatches",
        example_path="examples/dispatcher/dispatches_examples",
        max_workers=PRODUCER_WORKERS,
        max_queue_size=EVENT_QTY * 2,
    )
    await dispatcher.start()
    started_at = time.monotonic()
    chunk_size = (EVENT_QTY + PRODUCER_WORKERS - 1) // PRODUCER_WORKERS
    tasks = []
    for worker_id in range(PRODUCER_WORKERS):
        start_index = worker_id * chunk_size + 1
        end_index = min(EVENT_QTY + 1, start_index + chunk_size)
        if start_index >= end_index:
            continue
        tasks.append(asyncio.create_task(produce_events(dispatcher, start_index, end_index, 1000 + worker_id)))
    await asyncio.gather(*tasks)
    await dispatcher.flush()
    elapsed = time.monotonic() - started_at
    print(f"Enviados {EVENT_QTY} eventos em {elapsed:.2f}s ({EVENT_QTY / elapsed:.2f}/s)")
    await dispatcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
