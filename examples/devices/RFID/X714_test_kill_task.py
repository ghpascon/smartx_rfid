from smartx_rfid.devices import X714
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

devices = []


def on_tag_event(name: str, tag_data: dict):
    """Callback for when a tag is read"""
    print(f"🏷️  Tag Read: {tag_data}")
    print()


def on_x714_event(name: str, event_type: str, event_data=None):
    """General event handler for X714 events"""
    global devices
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(name, event_data)
        return
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    print()
    if event_type == "connected" and event_data:
        print("reset devices - closing old devices first")
        # close existing devices to release transports/tasks
        for device in list(devices):
            try:
                if hasattr(device, "close"):
                    if hasattr(device, "create_task"):
                        device.create_task(device.close())
                    else:
                        asyncio.create_task(device.close())
                elif hasattr(device, "shutdown"):
                    if hasattr(device, "create_task"):
                        device.create_task(device.shutdown())
                    else:
                        asyncio.create_task(device.shutdown())
            except Exception as e:
                logging.warning(f"Error closing device {getattr(device, 'name', str(device))}: {e}")

        # create and start fresh devices
        devices = create_devices()
        for device in devices:
            if hasattr(device, "create_task"):
                device.create_task(device.connect())
            else:
                asyncio.create_task(device.connect())


def create_devices():
    _devices = []
    _devices.append(
        X714(
            name="X714",
            start_reading=True,
            # port="/COM3"
        )
    )
    _devices[-1].on_event = on_x714_event
    return _devices


async def main():
    # === SERIAL EXAMPLE ===
    global devices
    devices = create_devices()
    for device in devices:
        asyncio.create_task(device.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)
        # await x714_serial.start_inventory() if not x714_serial.is_reading else await x714_serial.stop_inventory()


if __name__ == "__main__":
    asyncio.run(main())
