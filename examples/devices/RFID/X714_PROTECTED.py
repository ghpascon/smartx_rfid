from smartx_rfid.devices import X714
from smartx_rfid.utils import TagList
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

tags = TagList()
protected_inventory: bool = False
XPAD = X714(
    name="XPAD",
    start_reading=True,
    read_power=30,
    protected_inventory_active=protected_inventory,
    protected_inventory_password="12345678",
    session=0,
)


def on_tag(device: str, tag_data: dict):
    new_tag, tag = tags.add(tag_data, device=device)
    if new_tag:
        tag["descricao"] = "product ABC"  # Example of adding extra info to new tags
        logging.info(f"[ NEW TAG ] {tag}")
        if tag.get("epc") == "00000000000000000000000f":
            XPAD.protected_mode(tag.get("epc"))
    elif tag is not None:
        logging.info(f"[ EXISTING TAG ] {tag}")


def on_event(name: str, event_type: str, data):
    if event_type == "tag":
        on_tag(name, data)
    else:
        logging.info(f"Event from {name} - {event_type}: {data}")


async def main():
    global protected_inventory
    XPAD.on_event = on_event
    asyncio.create_task(XPAD.connect())
    while True:
        await asyncio.sleep(5)
        print("=" * 60)
        print(f"Total unique tags read: {len(tags)}")
        print()
        protected_inventory = not protected_inventory
        print(f"Changed protected_inventory to: {protected_inventory}")
        XPAD.protected_inventory(protected_inventory)


asyncio.run(main())
