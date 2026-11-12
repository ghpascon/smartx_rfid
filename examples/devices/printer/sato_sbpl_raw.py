"""Send raw SBPL code to a SATO printer (writes the EPC 112233445566 and prints it).

SBPL commands start with ESC (0x1B) and a job is delimited by ``<ESC>A`` ... ``<ESC>Z``.
``print()`` accepts a ``str``/``bytes`` job, replaces the literal text ``<ESC>`` by the ESC byte,
adds the STX/ETX framing and tracks it (print_sent / print_success / print_error).
``write()`` sends the bytes exactly as given.
"""

import asyncio
import logging

from smartx_rfid.devices import SatoSbplPrinter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

printer = SatoSbplPrinter(ip="192.168.1.112", port=9100, auto_rfid_result=True)

EPC = "112233445566"

# Print position (dots, 203 dpi = ~8 dots/mm), measured from the base reference point.
# If the text lands outside the label, shift the base reference point with BASE_V / BASE_H
# (signed dots, <A3>) or change POS_V / POS_H.
BASE_V = 0
BASE_H = 0
POS_V = 100
POS_H = 100

# Raw SBPL job with the literal "<ESC>" tag: RFID write + one line of text.
RAW_SBPL = (
    "<ESC>A"
    f"<ESC>A3V{BASE_V:+06d}H{BASE_H:+05d}"  # base reference point correction
    "<ESC>RU,01"  # return the write result (read with DC2 PK)
    f"<ESC>IP0e:h,epc:{EPC};"  # write the EPC on the tag
    f"<ESC>V{POS_V}<ESC>H{POS_H}<ESC>XM{EPC}"  # vertical / horizontal position + font XM text
    "<ESC>Q1"  # quantity
    "<ESC>Z"
)


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")
    if event_type == "status" and event_data == "ready" and not getattr(on_event, "sent", False):
        # print(): framing (STX/ETX) added automatically, job tracked until the printer is idle.
        ok, result = printer.print(RAW_SBPL)
        on_event.sent = ok
        print(f"Print sent, ID: {result}" if ok else f"Print error: {result}")
    if event_type == "rfid_result":
        print(f"EPC: {event_data['epc']}  TID: {event_data['tid']}  success: {event_data['success']}")
        raise SystemExit(0)
    if event_type == "print_error":
        raise SystemExit(1)


async def main():
    printer.on_event = on_event
    asyncio.create_task(printer.connect())

    while not printer.can_print:
        await asyncio.sleep(0.5)

    # Alternative: write() sends bytes untouched (you provide STX/ETX), with no tracking.
    # await printer.write(b"\x02" + RAW_SBPL.replace("<ESC>", "\x1b").encode("cp858") + b"\x03")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
