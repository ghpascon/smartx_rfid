from smartx_rfid.devices.printer import SatoPrinter, params_zpl_example
import asyncio
import logging
from smartx_rfid.utils.printer import generate_zpl_with_params

printer = SatoPrinter(ip="192.168.1.112")

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_event(name: str, event_type: str, event_data=None):
    print(f"{name} -> Event: {event_type}, Data: {event_data}")


def generate_zpl_list(start=1, count=5):
    zpl_list = []
    for i in range(start, start + count):
        zpl = generate_zpl_with_params(
            params_zpl_example,
            epc=str(i).zfill(24),
            sequential=str(i).zfill(3),
        )
        zpl_list.append(zpl)
    return zpl_list


async def main():
    zpl_list = generate_zpl_list()
    print("Generated ZPL List:", zpl_list)
    printer.add_to_print_queue(zpl_list)
    printer.on_event = on_event
    asyncio.create_task(printer.connect())

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
