from smartx_rfid.devices import SERIAL
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_serial_event(event_type: str, event_data=None):
    print(f"Event: {event_type}, Data: {event_data}")


async def main():
    serial_device = SERIAL(
        name="SerialDevice",
    )
    serial_device.on_event = on_serial_event

    asyncio.create_task(serial_device.connect())

    # Keep the main function running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
