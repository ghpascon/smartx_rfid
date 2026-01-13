from smartx_rfid.devices import X714  # Use X714 to get the tags
from smartx_rfid.utils import TagList
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

tags = TagList()


def on_tag(device: str, tag_data: dict):
    tags.add(tag_data, device=device)


def on_event(name: str, event_type: str, data):
    if event_type == "tag":
        on_tag(name, data)
    else:
        print(f"Event from {name} - {event_type}: {data}")


async def main():
    device = X714(name="Smartx Reader", start_reading=True, read_power=30)
    device.on_event = on_event
    asyncio.create_task(device.connect())
    while True:
        await asyncio.sleep(5)
        print("=" * 60)
        print(f"Total unique tags read: {len(tags)}")
        print()


asyncio.run(main())
