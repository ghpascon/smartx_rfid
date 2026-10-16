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
pending_writes: set[str] = set()
acupad = ACUPAD(
    name="ACUPAD",
    active_ant=[1, 2],
    start_reading=True,
    read_power=23,
    session=0,
    read_tid=True,
    beep=True,
)
epc_prefix = "111"


async def write_epc_safe(tag_data: dict):
    tag_target = (tag_data or {}).get("tid", "")
    if not tag_target:
        return

    if tag_target in pending_writes:
        return
    pending_writes.add(tag_target)

    try:
        ok = await acupad.write_epc(
            None,
            tag_target,
            epc_prefix + tag_target[len(epc_prefix) :],
            "00000000",
        )
        if not ok:
            logging.info("Write skipped for EPC %s (tag not found anymore)", tag_target)
    except Exception as exc:
        logging.warning("Write EPC failed for %s: %s", tag_target, exc)
    finally:
        pending_writes.discard(tag_target)


def on_tag_event(name: str, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"🏷️  Tag Read: {tag_data}")
    if not tag_data.get("epc", "").startswith(epc_prefix):
        asyncio.create_task(write_epc_safe(tag_data))
        return
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
    acupad.on_event = on_event
    asyncio.create_task(acupad.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(3)
        logging.info(f"Total Tags Read: {len(tags)}")


if __name__ == "__main__":
    asyncio.run(main())
