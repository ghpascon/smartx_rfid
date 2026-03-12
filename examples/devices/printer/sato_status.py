from smartx_rfid.devices.printer import SatoPrinter
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


async def main():
    printer = SatoPrinter(ip="192.168.1.112")

    asyncio.create_task(printer.connect())

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
