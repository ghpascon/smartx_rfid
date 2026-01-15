# SmartX RFID

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![Version](https://img.shields.io/badge/version-1.5.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Python library for RFID device integration and data management.

## Installation

```bash
pip install smartx-rfid
```

## Quick Start

```python
from smartx_rfid.devices import X714
import asyncio

async def on_tag_read(name: str, tag_data: dict):
    print(f"Tag: {tag_data['epc']} | RSSI: {tag_data['rssi']}dBm")

async def main():
    reader = X714(name="RFID Reader", start_reading=True)
    reader.on_event = lambda name, event_type, data: (
        asyncio.create_task(on_tag_read(name, data)) 
        if event_type == "tag" else None
    )
    
    await reader.connect()
    
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```

## Features

### Supported Devices
- **X714 RFID Reader** - Serial, TCP, Bluetooth LE connections
- **R700 IOT** - HTTP REST API integration
- **Generic Serial/TCP** - Custom protocol support

### Core Components
- **Device Management** - Async communication with auto-reconnection
- **Database Integration** - SQLAlchemy with multiple database support
- **Webhook System** - HTTP notifications with retry logic
- **Tag Management** - Thread-safe tag list with deduplication

## Device Examples

### X714 RFID Reader

```python
from smartx_rfid.devices import X714

# Serial connection (auto-detect)
reader = X714(name="X714-Serial")

# TCP connection
reader = X714(
    name="X714-TCP", 
    connection_type="TCP", 
    ip="192.168.1.100"
)

# Bluetooth LE
reader = X714(
    name="X714-BLE", 
    connection_type="BLE"
)

def on_event(name: str, event_type: str, data: dict):
    if event_type == "tag":
        print(f"EPC: {data['epc']}, Antenna: {data['ant']}")

reader.on_event = on_event
await reader.connect()
```

### R700 IOT Reader

```python
from smartx_rfid.devices import R700_IOT, R700_IOT_config_example

reader = R700_IOT(
    name="R700-Reader",
    ip="192.168.1.200",
    config=R700_IOT_config_example
)

reader.on_event = on_event
await reader.connect()
```

## Database Integration

```python
from smartx_rfid.db import DatabaseManager
from sqlalchemy import Column, String, Float, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class TagModel(Base):
    __tablename__ = 'rfid_tags'
    
    id = Column(Integer, primary_key=True)
    epc = Column(String(50), unique=True, nullable=False)
    tid = Column(String(50))
    ant = Column(Integer)
    rssi = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

# Initialize database
db = DatabaseManager("sqlite:///rfid_tags.db")
db.register_models(TagModel)
db.create_tables()

# Use with sessions
with db.get_session() as session:
    tag = TagModel(epc="E200001175000001", ant=1, rssi=-45.2)
    session.add(tag)

# Raw SQL queries
results = db.execute_query_fetchall(
    "SELECT * FROM rfid_tags WHERE rssi > :threshold",
    params={"threshold": -50}
)
```

### Supported Databases
- PostgreSQL: `postgresql://user:pass@localhost/db`
- MySQL: `mysql+pymysql://user:pass@localhost/db`
- SQLite: `sqlite:///path/to/database.db`

## Webhook Integration

```python
from smartx_rfid.webhook import WebhookManager

webhook = WebhookManager("https://api.example.com/rfid-events")

# Send tag data
success = await webhook.post("device_01", "tag_read", {
    "epc": "E200001175000001",
    "rssi": -45.2,
    "antenna": 1,
    "timestamp": "2026-01-15T10:30:00Z"
})

if success:
    print("Webhook sent successfully")
```

## Tag Management

```python
from smartx_rfid.utils import TagList

# Create thread-safe tag list
tags = TagList(unique_identifier="epc")

def on_tag(device: str, tag_data: dict):
    new_tag, tag = tags.add(tag_data, device=device)
    
    if new_tag:
        print(f"New tag: {tag['epc']}")
        # Add custom data
        tag['product_name'] = "Widget ABC"
    else:
        print(f"Existing tag: {tag['epc']}")

# Use with device events
reader.on_event = lambda name, event_type, data: (
    on_tag(name, data) if event_type == "tag" else None
)
```

## Complete Integration Example

```python
import asyncio
from smartx_rfid.devices import X714
from smartx_rfid.db import DatabaseManager
from smartx_rfid.webhook import WebhookManager
from smartx_rfid.utils import TagList

async def rfid_system():
    # Initialize components
    reader = X714(name="Production-Scanner", start_reading=True)
    db = DatabaseManager("postgresql://localhost/rfid_production")
    webhook = WebhookManager("https://api.internal.com/rfid")
    tags = TagList()
    
    async def process_tag(name: str, tag_data: dict):
        # Check if new tag
        new_tag, tag = tags.add(tag_data, device=name)
        
        if new_tag:
            # Save to database
            with db.get_session() as session:
                session.add(TagModel(**tag_data))
            
            # Send notification
            await webhook.post(name, "new_tag", tag_data)
            print(f"New tag processed: {tag_data['epc']}")
    
    reader.on_event = lambda n, t, d: (
        asyncio.create_task(process_tag(n, d)) if t == "tag" else None
    )
    
    await reader.connect()

asyncio.run(rfid_system())
```

## Configuration

### Device Configuration
```python
# High-performance settings
reader = X714(
    name="FastScanner",
    read_power=30,      # Max power
    session=2,          # Session config
    read_interval=100   # Fast scanning
)

# Database with connection pooling
db = DatabaseManager(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=10,
    max_overflow=20,
    echo=True  # Enable SQL logging
)
```

### Logging Setup
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

## API Reference

### Core Modules
- `smartx_rfid.devices` - Device communication classes
- `smartx_rfid.db` - Database management
- `smartx_rfid.webhook` - HTTP notification system
- `smartx_rfid.utils` - Utility classes and helpers

### Event System
All devices use a consistent event callback system:

```python
def on_event(device_name: str, event_type: str, event_data: dict):
    """
    Event types:
    - "connected": Device connected successfully
    - "disconnected": Device disconnected
    - "tag": RFID tag detected
    - "error": Error occurred
    """
    pass

device.on_event = on_event
```

## Examples

The `examples/` directory contains working examples for all supported devices and features:

```
examples/
├── devices/
│   ├── RFID/           # X714, R700_IOT examples
│   └── generic/        # Serial, TCP examples
├── db/                 # Database integration examples
└── utils/              # Tag management examples
```

Run examples:
```bash
python examples/devices/RFID/X714_SERIAL.py
python examples/db/showcase.py
```

## Requirements

- Python 3.11+
- Dependencies automatically installed with pip

## License

MIT License

## Support

- **Repository**: [https://github.com/ghpascon/smartx_rfid](https://github.com/ghpascon/smartx_rfid)
- **Issues**: [GitHub Issues](https://github.com/ghpascon/smartx_rfid/issues)
- **Email**: [gh.pascon@gmail.com](mailto:gh.pascon@gmail.com)
