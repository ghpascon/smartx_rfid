import asyncio
import importlib
import logging
import random
import sys
import time

from smartx_rfid.dispatcher import EventDispatcher


logging.basicConfig(level=logging.INFO)

EVENT_QTY = 10_000
PRODUCER_WORKERS = 30
DISPATCHER_WORKERS_DEFAULT = PRODUCER_WORKERS
POST_WORKERS_MIN = 10
POST_WORKERS_MULTIPLIER = 2
HTTP2_ENABLED_DEFAULT = True
CONCURRENT_POST_WORKERS = 4


def build_epc(index: int) -> str:
    # EPC sequencial com 24 caracteres hexadecimais.
    return f"{index:024X}"


def build_tid_from_epc(epc: str) -> str:
    # TID baseado no EPC mantendo 24 caracteres hexadecimais.
    return f"E280{epc[4:]}"


async def produce_events(
    dispatcher: EventDispatcher,
    start_index: int,
    end_index: int,
    seed: int,
) -> tuple[int, int]:
    rng = random.Random(seed)
    accepted = 0
    dropped = 0

    for index in range(start_index, end_index):
        epc = build_epc(index)
        tid = build_tid_from_epc(epc)
        device = "XPAD" if rng.randint(0, 1) == 0 else "R700"
        ant = rng.randint(1, 4)

        ok = await dispatcher.add_async(
            device,
            "tag",
            {
                "epc": epc,
                "tid": tid,
                "ant": ant,
                "rssi": -50,
            },
        )
        if ok:
            accepted += 1
        else:
            dropped += 1

    return accepted, dropped


async def main() -> None:
    n_events = int(sys.argv[1]) if len(sys.argv) > 1 else EVENT_QTY
    producer_workers = int(sys.argv[2]) if len(sys.argv) > 2 else PRODUCER_WORKERS
    dispatcher_workers = int(sys.argv[3]) if len(sys.argv) > 3 else DISPATCHER_WORKERS_DEFAULT
    post_workers = (
        int(sys.argv[4]) if len(sys.argv) > 4 else max(POST_WORKERS_MIN, dispatcher_workers * POST_WORKERS_MULTIPLIER)
    )
    http2_enabled = bool(int(sys.argv[5])) if len(sys.argv) > 5 else HTTP2_ENABLED_DEFAULT
    post_worker_concurrency = int(sys.argv[6]) if len(sys.argv) > 6 else CONCURRENT_POST_WORKERS

    dispatcher = EventDispatcher(
        dispatches_path="examples/dispatcher/dispatches",
        example_path="examples/dispatcher/dispatches_examples",
        max_workers=dispatcher_workers,
        max_queue_size=max(50_000, n_events * 4),
        post_workers=post_workers,
        post_worker_concurrency=post_worker_concurrency,
        post_queue_max_size=max(50_000, n_events * 4),
        suppress_httpx_request_logs=True,
        http2_enabled=http2_enabled,
    )

    await dispatcher.start()

    started_at = time.monotonic()
    chunk_size = max(1, (n_events + producer_workers - 1) // producer_workers)
    tasks: list[asyncio.Task[tuple[int, int]]] = []

    for worker_id in range(producer_workers):
        start_index = worker_id * chunk_size + 1
        end_index = min(n_events + 1, start_index + chunk_size)
        if start_index >= end_index:
            continue

        tasks.append(
            asyncio.create_task(
                produce_events(
                    dispatcher=dispatcher,
                    start_index=start_index,
                    end_index=end_index,
                    seed=1000 + worker_id,
                )
            )
        )

    results = await asyncio.gather(*tasks)
    await dispatcher.flush(timeout=120)

    elapsed = time.monotonic() - started_at
    accepted = sum(item[0] for item in results)
    dropped = sum(item[1] for item in results)
    throughput = accepted / elapsed if elapsed > 0 else 0.0
    stats = dispatcher.get_stats()

    print("==== LOAD TEST RESULT ====")
    print(f"n_events={n_events}")
    print(f"producer_workers={producer_workers}")
    print(f"dispatcher_workers={dispatcher_workers}")
    print(f"post_workers={post_workers}")
    print(f"post_worker_concurrency={post_worker_concurrency}")
    print(f"http2_enabled={http2_enabled}")
    print(f"accepted={accepted} dropped={dropped}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"enqueue_throughput_events_per_sec={throughput:.2f}")
    print(f"dispatcher_stats={stats}")
    print(
        f"SUMMARY producer_workers={producer_workers} dispatcher_workers={dispatcher_workers} "
        f"events={n_events} elapsed_seconds={elapsed:.3f}"
    )

    await dispatcher.stop(drain=True)


if __name__ == "__main__":
    try:
        uvloop = importlib.import_module("uvloop")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
