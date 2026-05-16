"""
TagList Performance Test
Run with: python examples/utils/taglist_performance.py
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from smartx_rfid.utils import TagList

TOTAL_TAGS = 100_000


def make_tag(epc: str, tid: str | None, rssi: int, antenna: int) -> dict:
    tag = {"epc": epc, "rssi": rssi, "antenna": antenna}
    if tid is not None:
        tag["tid"] = tid
    return tag


def main():
    tag_list = TagList()
    half = TOTAL_TAGS // 2

    print("=== TagList Performance Test ===")
    print(f"Total inserts : {TOTAL_TAGS}")
    print(f"Duplicates    : {half} (mesmo EPC, rssi/ant variando)")
    print(f"Unique        : {half} (EPCs distintos)")
    print()

    new_count = 0
    update_count = 0

    def add_dup(i: int):
        tag = make_tag(
            "E28011606000020000000001",
            "E28011052000701234567890",
            -(50 + (i % 20)),
            (i % 4) + 1,
        )
        return tag_list.add(tag, "reader-dup")

    def add_unique(i: int):
        epc = f"E280110000{i:014X}"
        tag = make_tag(epc, None, -(40 + (i % 30)), (i % 4) + 1)
        return tag_list.add(tag, "reader-unique")

    start = time.perf_counter()

    with ThreadPoolExecutor() as executor:
        # Metade: EPC duplicado — simula re-leituras da mesma tag
        dup_futures = [executor.submit(add_dup, i) for i in range(half)]
        # Metade: EPCs únicos — simula tags novas
        unique_futures = [executor.submit(add_unique, i) for i in range(half)]

        for future in as_completed(dup_futures + unique_futures):
            is_new, _ = future.result()
            if is_new:
                new_count += 1
            else:
                update_count += 1

    elapsed = time.perf_counter() - start

    print("Results:")
    print(f"  New insertions : {new_count}")
    print(f"  Updates        : {update_count}")
    print(f"  Final list len : {len(tag_list)} unique keys")
    print()
    print(f"Elapsed time     : {elapsed:.3f}s")
    print(f"Throughput       : {TOTAL_TAGS / elapsed:.0f} ops/s")


if __name__ == "__main__":
    main()
