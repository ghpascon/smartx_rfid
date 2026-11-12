"""Queue several SBPL jobs and track them until every label is printed."""

import asyncio
import logging

from smartx_rfid.devices import SatoSbplPrinter
from smartx_rfid.devices.printer import SbplLabel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

printer = SatoSbplPrinter(ip="192.168.1.112", port=9100)
pending_ids: set[str] = set()


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} -> {event_type}: {event_data}")
    if event_type == "print_success":
        pending_ids.discard(event_data)
    if event_type == "print_error":
        print(f"Job {event_data} failed. Remaining in queue: {printer.print_queue_size}")
        pending_ids.discard(event_data)


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())

    labels = [
        SbplLabel().text(f"LABEL {i}", "XM", x=50, y=50, scale=3).code128(f"{i:010d}", x=50, y=150) for i in range(1, 6)
    ]
    # Jobs are snapshotted when queued and sent one at a time, only when the printer is ready.
    pending_ids.update(printer.add_to_print_queue(labels))

    while pending_ids:
        await asyncio.sleep(0.5)
    print("All labels printed.")
    await printer.close()


if __name__ == "__main__":
    asyncio.run(main())
