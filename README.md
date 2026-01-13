# SmartX RFID

The official SmartX RFID Python library for seamless integration with RFID systems and devices.

## Overview

SmartX RFID is a comprehensive Python package designed to provide easy-to-use interfaces for RFID operations and device management. This library serves as the foundation for building robust RFID applications.

## Features (Current & Planned)

- **Device Communication**: Asynchronous serial communication with RFID devices
- **Auto-Detection**: Automatic port detection for USB devices by VID/PID
- **Connection Management**: Automatic reconnection and error handling
- **External Device Support**: Interface with various RFID readers and writers *(coming soon)*
- **Tag Operations**: Read, write, and manage RFID tags *(coming soon)*
- **Protocol Support**: Multiple RFID protocols and standards *(coming soon)*

## Installation

```bash
pip install smartx-rfid
```

## Quick Start

```python
from smartx_rfid.devices import SERIAL
import asyncio

async def main():
    device = SERIAL(name="MyRFIDDevice")
    await device.connect()

asyncio.run(main())
```

## Development Status

This library is actively under development. Current focus areas include:

- Core device communication protocols
- External device integration
- Enhanced error handling
- Comprehensive documentation

## License

MIT License

## Support

For issues and support, please visit our [GitHub repository](https://github.com/ghpascon/smartx_rfid).
