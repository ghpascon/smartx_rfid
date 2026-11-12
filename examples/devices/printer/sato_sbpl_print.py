"""Print a complete SBPL label (text, barcodes, 2D codes and shapes) on a SATO printer.

SBPL features not available in ZPL printers (e.g. scalable fonts, Aztec, form overlays) are
available through the ``SbplLabel`` builder.
"""

import asyncio
import logging

from smartx_rfid.devices import SatoSbplPrinter
from smartx_rfid.devices.printer import SbplLabel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

printer = SatoSbplPrinter(ip="192.168.1.112", port=9100)


def build_label() -> SbplLabel:
    return (
        SbplLabel()
        .darkness(3)
        .speed(4)
        .box(width=760, height=480, x=20, y=20, thickness=4)
        .text("SMARTX LOGISTICA", "XM", x=50, y=50, scale=2)
        .line(length=700, x=50, y=110, width=3)
        .scalable_text("Produto de teste", width=40, height=40, x=50, y=130)
        .code128("1234567890", x=50, y=200, narrow=2, height=100)
        .qr_code("https://smartx.example/item/1234567890", x=450, y=190, cell=5)
        .data_matrix("1234567890", x=50, y=360, cell=5)
        .quantity(1)
    )


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")
    if event_type == "status" and event_data == "ready" and not getattr(on_event, "sent", False):
        ok, result = printer.print(build_label())
        on_event.sent = ok
        print(f"Print sent, ID: {result}" if ok else f"Print error: {result}")
    if event_type in ("print_success", "print_error"):
        raise SystemExit(0)


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
