from smartx_rfid.devices import X714
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_tag_event(name: str, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"🏷️  Tag Read: {tag_data}")
    print()


def on_x714_event(name: str, event_type: str, event_data=None):
    """General event handler for X714 events"""
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(name, event_data)
        return
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    print()


async def main():
    # === SERIAL EXAMPLE ===
    print("=== X714 SERIAL Example ===")
    x714_serial = X714(
        name="X714",
        start_reading=True,
        # port="/COM3"
    )
    x714_serial.on_event = on_x714_event
    asyncio.create_task(x714_serial.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)
        # await x714_serial.start_inventory() if not x714_serial.is_reading else await x714_serial.stop_inventory()


if __name__ == "__main__":
    asyncio.run(main())
