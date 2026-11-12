"""Read the RFID tag currently in front of the SATO SBPL printer antenna (``DC2 PJ``)."""

import asyncio
import logging

from smartx_rfid.devices import SatoSbplPrinter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

printer = SatoSbplPrinter(ip="192.168.1.112", port=9100)


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())

    while not printer.is_connected or printer.last_status is None:
        await asyncio.sleep(0.5)

    while True:
        # areas: "epc", "tid", "user", "pc". The read is refused while the printer is printing.
        tag = await printer.read_rfid(("epc", "tid"))
        if tag is None:
            print("No reply (printer busy or timeout).")
        elif tag["error"]:
            print("No tag found.")
        else:
            print(f"EPC: {tag.get('epc')}  TID: {tag.get('tid')}")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
