import logging
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import uvicorn

from smartx_rfid.devices import DeviceManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


DEVICE_NAME = os.getenv("X714_DEVICE_NAME", "MESA_3_4")
X714_HOST = os.getenv("X714_HOST", "smtx-7cbe799205d4.local")
X714_PORT = int(os.getenv("X714_PORT", "23"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8014"))


class RuntimeState:
    def __init__(self):
        self.tmpdir: tempfile.TemporaryDirectory | None = None
        self.manager: DeviceManager | None = None


state = RuntimeState()


def on_event(name: str, event_type: str, event_data=None):
    logging.info("[EVENT] %s - %s: %s", name, event_type, event_data)


def build_x714_config() -> dict:
    return {
        "reader": "X714",
        "connection_type": "TCP",
        "ip": X714_HOST,
        "tcp_port": X714_PORT,
        "buzzer": False,
        "session": 1,
        "start_reading": True,
        "gpi_start": False,
        "protected_inventory_active": False,
        "protected_inventory_password": "12345678",
        "active_ant": [1, 2, 3, 4],
        "read_power": 25,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.tmpdir = tempfile.TemporaryDirectory(prefix="smartx-rfid-devices-")
    state.manager = DeviceManager(devices_path=state.tmpdir.name, event_func=on_event)

    ok, err = await state.manager.create_device_config(DEVICE_NAME, build_x714_config(), overwrite=True)
    if not ok:
        raise RuntimeError(f"Failed to create device config: {err}")

    await state.manager.connect_devices(force=True)
    logging.info("FastAPI started with temp devices path: %s", state.tmpdir.name)
    try:
        yield
    finally:
        try:
            if state.manager is not None:
                await state.manager.shutdown()
        finally:
            if state.tmpdir is not None:
                state.tmpdir.cleanup()
            state.manager = None
            state.tmpdir = None
            logging.info("FastAPI shutdown complete")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "device_name": DEVICE_NAME,
        "x714_host": X714_HOST,
        "x714_port": X714_PORT,
    }


@app.get("/devices")
async def devices_status():
    if state.manager is None:
        raise HTTPException(status_code=503, detail="Device manager not initialized")
    return {
        "count": state.manager.get_device_count(),
        "devices": state.manager.get_device_info(),
    }


@app.post("/reconnect")
async def reconnect_devices():
    if state.manager is None:
        raise HTTPException(status_code=503, detail="Device manager not initialized")
    await state.manager.connect_devices(force=True)
    return {"ok": True}


@app.post("/inventory/{device_name}/{action}")
async def inventory(device_name: str, action: str):
    if state.manager is None:
        raise HTTPException(status_code=503, detail="Device manager not initialized")

    action = action.lower().strip()
    if action == "start":
        ok = await state.manager.start_inventory(device_name)
        return {"ok": ok, "action": "start", "device": device_name}
    if action == "stop":
        ok = await state.manager.stop_inventory(device_name)
        return {"ok": ok, "action": "stop", "device": device_name}

    raise HTTPException(status_code=400, detail="Action must be 'start' or 'stop'")


def main():
    uvicorn.run(app, host=API_HOST, port=API_PORT, reload=False, log_level="info")


if __name__ == "__main__":
    main()
