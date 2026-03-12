from smartx_rfid.devices import R700_IOT
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


def on_r700_iot_event(name: str, event_type: str, event_data=None):
    """General event handler for R700_IOT events"""
    print("=" * 60)
    if event_type == "tag":
        on_tag_event(name, event_data)
        return
    print(f"{name} -> Event: {event_type}, Data: {event_data}")
    print()


async def main():
    # === SERIAL EXAMPLE ===
    print("=== R700 IOT Example ===")
    r700_iot = R700_IOT(
        name="R700_IOT",
        ip="impinj-14-46-36",
        active_ant=[1],
        read_power=14,
        start_reading=True,
        protected_inventory_active=True,
        protected_inventory_password="12345678",
    )
    print(r700_iot.reading_config)
    r700_iot.on_event = on_r700_iot_event
    print("Starting R700 IOT connection...")
    asyncio.create_task(r700_iot.connect())

    # Keep the main loop running
    is_protected = True
    while True:
        await asyncio.sleep(5)
        is_protected = not is_protected
        # success, error = await r700_iot.protected_inventory(is_protected)
        # if not success:
        #     print(f"Error setting protected inventory: {error}")
        # else:
        #     print(f"Protected inventory set to: {is_protected}")


if __name__ == "__main__":
    asyncio.run(main())
