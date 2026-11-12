"""Write an RFID tag on a SATO SBPL printer and read the EPC/TID result (``DC2 PK``)."""

import asyncio
import logging

from smartx_rfid.devices import SatoSbplPrinter
from smartx_rfid.devices.printer import SbplLabel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

EPC = "E2000000000000000000AAAA"

# auto_rfid_result=True emits an "rfid_result" event after every job that wrote a tag.
printer = SatoSbplPrinter(ip="192.168.1.112", port=9100, auto_rfid_result=True)


def build_label(epc: str) -> SbplLabel:
    return (
        SbplLabel()
        .rfid_power(write_dbm=20, read_dbm=20)
        .write_rfid(epc=epc, lock="00001")  # lock the EPC bank
        .text(epc, "XM", x=50, y=50, scale=2)
        .code128(epc, x=50, y=120, height=80)
    )


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")
    if event_type == "status" and event_data == "ready" and not getattr(on_event, "sent", False):
        ok, result = printer.print(build_label(EPC))
        on_event.sent = ok
        print(f"Print sent, ID: {result}" if ok else f"Print error: {result}")
    if event_type == "rfid_result":
        print(f"EPC: {event_data['epc']}  TID: {event_data['tid']}  success: {event_data['success']}")
        raise SystemExit(0)
    if event_type == "print_error":
        print("Print failed (check tag, antenna power or RFID error status).")
        raise SystemExit(1)


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
