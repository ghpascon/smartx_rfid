"""Print raw SBPL jobs through the DeviceManager print queue (SATO_SBPL).

The device name is the JSON file name (``devices/SATO_SBPL.json`` -> ``"SATO_SBPL"``).
Jobs added with ``add_to_print_queue`` are sent one at a time, as soon as the printer is ready.

A raw SBPL job must:
- start with ``<ESC>A`` and end with ``<ESC>Z``;
- contain ``<ESC>Q<quantity>`` before ``<ESC>Z`` (without it the printer receives the job but prints nothing);
- use SBPL commands only (``<ESC>XM`` text, ``<ESC>IP0`` RFID write ...). ZPL-style commands such as
  ``<ESC>XA`` or ``<ESC>RFW,H,12,...`` do not exist in SBPL.

The literal text ``<ESC>`` is replaced by the ESC byte (0x1B) by the driver.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from smartx_rfid.devices import DeviceManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

DEVICE_NAME = "SATO_SBPL"
pending_ids: set[str] = set()


def build_job(epc: str) -> str:
    """Write ``epc`` (HEX, multiple of 4 digits) on the tag and print it as text."""
    return (
        "<ESC>A"
        "<ESC>RU,01"  # keep the write result available (DC2 PK)
        f"<ESC>IP0e:h,epc:{epc};"  # RFID write
        "<ESC>H0100<ESC>V0100<ESC>L0202"  # position 100/100 and enlargement 2x2
        f"<ESC>XMEPC: {epc}"  # text with the XM font
        "<ESC>Q1"  # print quantity (required)
        "<ESC>Z"
    )


def on_event(device: dict, event_type: str, event_data=None):
    if event_type == "device_info":
        return
    print(f"{device.get('name')} -> {event_type}: {event_data}")
    if event_type in ("print_success", "print_error", "print_sent_error"):
        print_id = event_data.get("id") if isinstance(event_data, dict) else event_data
        pending_ids.discard(print_id)


async def main():
    # DeviceManager loads every JSON of a folder; copy only the SBPL one.
    folder = Path(tempfile.mkdtemp())
    shutil.copy(Path(__file__).resolve().parents[3] / "devices" / "SATO_SBPL.json", folder)

    manager = DeviceManager(devices_path=str(folder), event_func=on_event)
    asyncio.create_task(manager.connect_devices())
    await asyncio.sleep(0.5)  # let the manager load the devices

    # One job, or a list of jobs (a list returns a list of ids).
    epcs = ["000000000001", "000000000002"]
    ids = manager.add_to_print_queue(DEVICE_NAME, [build_job(epc) for epc in epcs])
    if not ids:
        print("Could not add to the print queue (device not found?).")
        return
    for epc, print_id in zip(epcs, ids):
        print(f"Queued EPC {epc} -> id {print_id}")
    pending_ids.update(ids)

    while pending_ids:
        await asyncio.sleep(0.5)
    print("All jobs finished.")


if __name__ == "__main__":
    asyncio.run(main())
