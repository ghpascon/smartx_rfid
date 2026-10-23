import logging
from typing import Any


def normalize_device(device: Any) -> dict:
    """
    Normalize a device identifier into a dict ``{"name": ..., "serial_number": ...}``.

    Accepts a dict (extra keys are preserved) or a plain string, which is
    treated as the device name.
    """
    if isinstance(device, dict):
        result = dict(device)
        result["name"] = result.get("name") or "UNKNOWN"
        result.setdefault("serial_number", None)
        return result
    name = "UNKNOWN" if device is None else str(device)
    return {"name": name, "serial_number": None}


def on_event(device: dict | str, event_type: str, event_data=None):
    """
    Default event handler for protocol events.

    This method can be overridden to handle specific events like
    connection status changes or received messages.

    Args:
            device: Dict with ``name`` and ``serial_number`` of the device
                    (a plain string is treated as the device name).
            event_type: Type of event ('connection', 'receive', etc.)
            event_data: Associated data with the event
    """
    device = normalize_device(device)
    logging.info(
        f"{device.get('name')} (SN: {device.get('serial_number')}) -> 🔔 Event: {event_type}, Data: {event_data}"
    )
