"""Load a SATO SBPL printer from a JSON device file with the DeviceManager.

``devices/SATO_SBPL.json``::

    {"READER": "SATO_SBPL", "ip": "192.168.1.112", "port": 9100}
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from smartx_rfid.devices import DeviceManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")


def on_event(device: dict, event_type: str, event_data=None):
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> {event_type}: {event_data}")


async def main():
    # DeviceManager loads every JSON of a folder; copy only the SBPL one.
    folder = Path(tempfile.mkdtemp())
    shutil.copy(Path(__file__).resolve().parents[3] / "devices" / "SATO_SBPL.json", folder)

    manager = DeviceManager(devices_path=str(folder), event_func=on_event)
    asyncio.create_task(manager.connect_devices())

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
