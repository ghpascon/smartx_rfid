"""Monitor a SATO SBPL printer and use the SBPL-only query/control commands."""

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

    print("Model / serial:", printer.model, printer.serial_number)
    print("Device info:", await printer.get_device_info(timeout=5))
    print("Sensors:", await printer.get_sensor_info())
    print("Label pitch:", await printer.get_label_pitch())
    print("Settings (SB):", await printer.get_settings("SB"))
    status = await printer.get_printer_status()
    print("Status:", status.as_dict() if status else None)

    # Examples of control commands (uncomment to try):
    # await printer.set_settings({"SB": {"SPEED": 4}})
    # await printer.feed()
    # await printer.reprint()
    # await printer.cancel_print()
    # print(await printer.read_rfid(("epc", "tid")))

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
