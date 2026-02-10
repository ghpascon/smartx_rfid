from smartx_rfid.devices import R700_IOT, R700_IOT_config_example
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
    config = R700_IOT_config_example
    # config.pop("startTriggers")
    # config.pop("stopTriggers")
    r700_iot = R700_IOT(name="R700_IOT", reading_config=config, ip="impinj-14-46-36", start_reading=True)
    r700_iot.on_event = on_r700_iot_event
    print("Starting R700 IOT connection...")
    print("With config:", R700_IOT_config_example)
    asyncio.create_task(r700_iot.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(2)
        if not r700_iot.is_connected:
            continue

        await r700_iot.write_gpo(pin=1, state=True, control="pulsed", time=500)


if __name__ == "__main__":
    asyncio.run(main())
