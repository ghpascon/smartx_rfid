from smartx_rfid.devices.printer import SatoPrinter, simple_zpl_example
import asyncio
import logging

printer = SatoPrinter(ip="192.168.1.112")

print_list = [
    simple_zpl_example,
    simple_zpl_example.replace("000000000000000000000001", "000000000000000000000002"),
    simple_zpl_example.replace("000000000000000000000001", "000000000000000000000003"),
    simple_zpl_example.replace("000000000000000000000001", "000000000000000000000004"),
    simple_zpl_example.replace("000000000000000000000001", "000000000000000000000005"),
]

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_event(name: str, event_type: str, event_data=None):
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    if event_type == "status" and event_data == "ready":
        if len(print_list) == 0:
            print("No more labels to print.")
            exit(0)
        status, msg = printer.print(print_list.pop(0))
        if not status:
            print(f"Print error: {msg}")
        if status:
            print(f"Print sent, ID: {msg}")


async def main():
    printer.on_event = on_event

    asyncio.create_task(printer.connect())

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
