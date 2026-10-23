from smartx_rfid.devices import X714
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_tag_event(device: dict, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"🏷️  Tag Read: {tag_data}")
    print()


def on_x714_event(device: dict, event_type: str, event_data=None):
    """General event handler for X714 events"""
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(device, event_data)
        return
    print(f"{device.get('name')} (SN: {device.get('serial_number')}) -> Event: {event_type}, Data: {event_data}")
    print()


async def main():
    # === TCP EXAMPLE ===
    print("=== X714 TCP Example ===")
    x714_tcp = X714(
        name="X714",
        connection_type="TCP",
        ip="192.168.1.102",
        start_reading=True,
    )
    x714_tcp.on_event = on_x714_event
    asyncio.create_task(x714_tcp.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
