from smartx_rfid.devices.generic.TCP._main import TCP
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def on_tcp_event(name: str, event_type: str, event_data=None):
    print(f"{name} -> Event: {event_type}, Data: {event_data}")


async def main():
    tcp_device = TCP(
        name="TCPDevice",
        ip="192.168.1.100",  # Change to your device IP
        port=4001,  # Change to your device port
    )
    tcp_device.on_event = on_tcp_event

    # Start connection task
    asyncio.create_task(tcp_device.connect())

    # Example of sending data every 5 seconds
    async def send_periodic_data():
        await asyncio.sleep(2)  # Wait a bit for connection
        counter = 1
        while True:
            if tcp_device.is_connected:
                await tcp_device.write(f"Test message #{counter}")
                counter += 1
            await asyncio.sleep(5)

    # Start periodic data sending task
    asyncio.create_task(send_periodic_data())

    # Keep the main function running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if tcp_device.writer:
            tcp_device.writer.close()
            await tcp_device.writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
