import asyncio
import logging

from smartx_rfid.devices import R420


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_event(device: dict, event_type: str, event_data=None):
    name = device.get("name")
    if event_type == "tag":
        print(f"[{name}] TAG -> {event_data}")
        return
    print(f"[{name}] (SN: {device.get('serial_number')}) {event_type}: {event_data}")


async def main():
    # Default mode: EPC + TID
    reader = R420(
        name="R420",
        ip="192.168.1.243",
        start_reading=True,
        read_tid=True,
        active_ant=[1],
        session=0,
        read_power=20,
    )

    # EPC-only mode example:
    # reader = R420(name="R420", ip="192.168.1.100", start_reading=True, read_tid=False)

    reader.on_event = on_event
    asyncio.create_task(reader.connect())

    while True:
        await asyncio.sleep(2)
        logging.info(
            "connected=%s reading=%s serial=%s",
            reader.is_connected,
            reader.is_reading,
            reader.serial_number,
        )


if __name__ == "__main__":
    asyncio.run(main())
