from smartx_rfid.devices import R700_IOT
import asyncio
import logging

target_identifier = "epc"
target_epc = "000000000000000000000001"
new_epc = "000000000000000000000002"
password = "00000000"

r700_config = {
    "antennaConfigs": [
        {
            "antennaPort": 1,
            "estimatedTagPopulation": 16,
            "fastId": "enabled",
            "inventorySearchMode": "dual-target",
            "inventorySession": 0,
            "receiveSensitivityDbm": -80,
            "rfMode": 4,
            "transmitPowerCdbm": 2000,
        }
    ],
    "eventConfig": {
        "common": {"hostname": "disabled"},
        "tagInventory": {
            "epc": "disabled",
            "epcHex": "enabled",
            "xpcHex": "disabled",
            "tid": "disabled",
            "tidHex": "enabled",
            "antennaPort": "enabled",
            "transmitPowerCdbm": "disabled",
            "peakRssiCdbm": "enabled",
            "frequency": "disabled",
            "pc": "disabled",
            "lastSeenTime": "disabled",
            "phaseAngle": "disabled",
            "tagReporting": {
                "reportingIntervalSeconds": 0,
                "tagCacheSize": 2048,
                "antennaIdentifier": "antennaPort",
                "tagIdentifier": "epc",
            },
        },
    },
}

r700_iot = R700_IOT(
    name="R700_IOT",
    reading_config=r700_config,
    start_reading=True,
)

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
    if tag_data["epc"] == target_epc:
        r700_iot.write_epc(target_identifier, target_epc, new_epc, password)


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
    r700_iot.on_event = on_r700_iot_event
    print("Starting R700 IOT connection...")
    print("With config:", r700_config)
    asyncio.create_task(r700_iot.connect())

    # Keep the main loop running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
