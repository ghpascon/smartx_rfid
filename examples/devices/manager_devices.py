import asyncio
import logging
from smartx_rfid.devices import DeviceManager

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_tag_event(name: str, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"{name} 🏷️  Tag Read: {tag_data}")
    print()


def on_event(name: str, event_type: str, event_data=None):
    """General event handler"""
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(name, event_data)
        return
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    print()


async def main():
    devices = DeviceManager(devices_path="devices", event_func=on_event)
    asyncio.create_task(devices.connect_devices())

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
