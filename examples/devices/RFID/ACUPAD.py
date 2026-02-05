from smartx_rfid.devices import ACUPAD
import asyncio
import logging
from smartx_rfid.utils import TagList

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
tags = TagList(unique_identifier="tid")


def on_tag_event(name: str, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"🏷️  Tag Read: {tag_data}")
    print()
    tags.add(tag_data, device=name)


def on_event(name: str, event_type: str, event_data=None):
    """General event handler for X714 events"""
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(name, event_data)
        return
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    print()


async def main():
    # === SERIAL EXAMPLE ===
    print("=== ACUPAD SERIAL Example ===")
    acupad = ACUPAD(name="ACUPAD", active_ant=[2], start_reading=True)
    acupad.on_event = on_event
    asyncio.create_task(acupad.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(3)
        if not acupad.is_reading:
            tags.clear()
            await acupad.start_inventory()
        else:
            await acupad.stop_inventory()
            logging.info(f"Total Tags Read: {len(tags)}")


if __name__ == "__main__":
    asyncio.run(main())
