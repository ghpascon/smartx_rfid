import asyncio
import logging

from smartx_rfid.devices import R420

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
epc_prefix = "0000000000"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

_write_lock = asyncio.Lock()


def _handle_bg_task(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logging.info("background write task cancelled")
    except Exception as exc:
        logging.warning("background write task failed: %s", exc)


async def _write_epc_background(epc: str, tid: str | None) -> None:
    if _write_lock.locked():
        return

    new_epc = epc_prefix + epc[len(epc_prefix) :]

    async with _write_lock:
        try:
            await reader.write_epc(
                target_identifier="tid",
                target_value=tid,
                new_epc=new_epc,
                password="00000000",
            )
            logging.info("write_epc ok %s -> %s", epc, new_epc)
        except Exception as exc:
            logging.warning("write_epc failed for %s: %s", epc, exc)


def on_event(device: dict, event_type: str, event_data=None):
    name = device.get("name")
    print(f"[{name}] (SN: {device.get('serial_number')}) {event_type}: {event_data}")
    if event_type == "tag":
        print(f"[{name}] writing EPC for tag {event_data.get('epc')}")
        epc: str = event_data.get("epc")
        if not epc.startswith(epc_prefix):
            task = asyncio.create_task(_write_epc_background(epc, event_data.get("tid")))
            task.add_done_callback(_handle_bg_task)
            return
        print(f"[{name}] TAG -> {event_data}")
        return


async def main():
    reader.on_event = on_event
    asyncio.create_task(reader.connect())

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
