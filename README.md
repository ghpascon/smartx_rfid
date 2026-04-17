# SmartX RFID

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![Version](https://img.shields.io/badge/version-9.0.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Python library for SmartX RFID integrations: device communication, webhook delivery, database utilities, parsing, and support modules for production flows.

## Installation

```bash
pip install smartx-rfid
```

For development:

```bash
poetry install
```

## Main Modules

- smartx_rfid.devices
  - RFID: X714, R700_IOT, ACUPAD
  - Generic: SERIAL, TCP
  - Printers: SatoPrinter, SatoWs4Printer
  - DeviceManager
- smartx_rfid.webhook
  - WebhookManager
  - WebhookXtrack
- smartx_rfid.db
  - DatabaseManager
- smartx_rfid.auth
  - token and password helpers
- smartx_rfid.api
  - Omie and Xtrack API clients
- smartx_rfid.utils
  - TagList, AlertsManager, delayed_function, hash, regex helpers

## Quick Start (Device Events)

```python
import asyncio
from smartx_rfid.devices import X714


async def handle_tag(device_name: str, event_data: dict):
    print(f"[{device_name}] EPC={event_data.get('epc')} RSSI={event_data.get('rssi')}")


async def main():
    reader = X714(name="X714-Reader", start_reading=True)

    def on_event(device_name: str, event_type: str, event_data: dict):
        if event_type == "tag":
            asyncio.create_task(handle_tag(device_name, event_data))

    reader.on_event = on_event
    await reader.connect()

    while True:
        await asyncio.sleep(1)


asyncio.run(main())
```

## Webhook Manager

The webhook API now has two explicit sending methods:

- post_event: standardized event envelope
- post: custom payload POST

It is designed for burst traffic and includes:

- async client reuse (keep-alive)
- request concurrency limiter
- retry with exponential backoff for network errors, HTTP 429, and HTTP 5xx
- safe payload serialization for datetime/date, Decimal, bytes, custom objects, dict/list/tuple/set

### Constructor

```python
from smartx_rfid.webhook import WebhookManager

webhook = WebhookManager(
    url="https://api.example.com/webhook",  # base URL
    timeout=5.0,
    max_retries=2,
    max_concurrent_requests=50,
)
```

### post_event (standard payload)

```python
success = await webhook.post_event(
    device="reader-01",
    event_type="tag_read",
    event_data={"epc": "E200001175000001", "rssi": -45.2},
)
```

Payload format sent by post_event:

```json
{
  "device": "reader-01",
  "event_type": "tag_read",
  "event_data": {
    "epc": "E200001175000001",
    "rssi": -45.2
  }
}
```

### post (custom payload + optional URL override)

```python
from datetime import datetime
from decimal import Decimal

payload = {
    "type": "heartbeat",
    "status": "ok",
    "timestamp": datetime.utcnow(),
    "load": Decimal("0.73"),
}

success = await webhook.post(
    payload=payload,
    headers={"X-Source": "rfid-core"},
    url="https://api.example.com/custom-endpoint",  # optional
)
```

If url is not provided, WebhookManager uses the base URL configured in the constructor.

### High-Throughput Example

```python
import asyncio

webhook = WebhookManager(
    url="https://api.example.com/events",
    max_concurrent_requests=20,
    max_retries=2,
)

events = [{"index": i, "ok": True} for i in range(200)]
results = await asyncio.gather(*(webhook.post(payload=e) for e in events))

print(f"sent={sum(results)} failed={len(results) - sum(results)}")
await webhook.aclose()
```

Recommended pattern:

```python
async with WebhookManager(url="https://api.example.com/events") as webhook:
    await webhook.post_event("reader-01", "connected", {"status": "ok"})
```

### Migration Note

Previous usage:

```python
await webhook.post("device", "event_type", {"data": 1})
```

Current usage:

```python
await webhook.post_event("device", "event_type", {"data": 1})
```

For arbitrary payloads, use:

```python
await webhook.post(payload={"anything": "you need"})
```

## Database Example

```python
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase
from smartx_rfid.db import DatabaseManager


class Base(DeclarativeBase):
    pass


class TagModel(Base):
    __tablename__ = "rfid_tags"

    id = Column(Integer, primary_key=True)
    epc = Column(String(64), unique=True, nullable=False)
    rssi = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


db = DatabaseManager("sqlite:///rfid_tags.db")
db.register_models(TagModel)
db.create_tables()

with db.get_session() as session:
    session.add(TagModel(epc="E200001175000001", rssi=-45.2))
```

## Event Callback Contract

All devices share a consistent callback contract:

```python
def on_event(device_name: str, event_type: str, event_data: dict):
    # Common event_type values:
    # connected, disconnected, tag, error
    ...
```

## Examples Directory

The examples folder includes:

- examples/devices/RFID
- examples/devices/generic
- examples/devices/printer
- examples/db
- examples/api
- examples/email
- examples/license
- examples/smtx_db
- examples/utils

Run examples with:

```bash
python examples/devices/RFID/X714_SERIAL.py
python examples/db/showcase.py
```

## Running Tests

```bash
pytest
```

To run only webhook-related tests:

```bash
pytest tests/utils/test_serialization.py -k webhook
```

## Requirements

- Python 3.11+
- Works on Linux, macOS, and Windows (depending on device transport and drivers)

## License

MIT

## Support

- Repository: https://github.com/ghpascon/smartx_rfid
- Issues: https://github.com/ghpascon/smartx_rfid/issues
