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
    # === BLE EXAMPLE ===
    print("=== X714 BLE Example ===")
    x714_ble = X714(
        name="X714",
        connection_type="BLE",
        start_reading=True,
    )
    x714_ble.on_event = on_x714_event
    asyncio.create_task(x714_ble.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
