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
    devices_by_name: dict[str, X714] = {}
    counter = 0

    print("=== X714 SERIAL Example (kill/recreate test) ===")

    def start_device():
        nonlocal counter
        counter += 1
        name = f"X714-{counter}"
        dev = X714(name=name, start_reading=True)
        dev.on_event = lambda n, e, d=None: on_device_event(n, e, d)
        devices_by_name[dev.name] = dev
        # prefer device task tracking if available
        if hasattr(dev, "create_task"):
            dev.create_task(dev.connect())
        else:
            asyncio.create_task(dev.connect())
        return dev

    def on_device_event(name: str, event_type: str, event_data=None):
        on_x714_event(name, event_type, event_data)

        # When a device connects, shutdown all other devices and create a new one
        if event_type == "connected" and event_data is True:
            for n, other in list(devices_by_name.items()):
                if n == name:
                    continue
                # call `close()` if available, else `shutdown()`
                coro = None
                if hasattr(other, "close"):
                    coro = other.close()
                elif hasattr(other, "shutdown"):
                    coro = other.shutdown()
                if coro is not None:
                    try:
                        if hasattr(other, "create_task"):
                            other.create_task(coro)
                        else:
                            asyncio.create_task(coro)
                    except Exception:
                        pass
                devices_by_name.pop(n, None)

            # start a fresh device to reproduce connect/disconnect lifecycle
            start_device()

    # start first device
    start_device()

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
