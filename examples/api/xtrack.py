from smartx_rfid.api import ApiXtrack
import asyncio
import logging

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


async def main():
    api = ApiXtrack("http://shopee.smtx.com.br:6102/req")
    success, response = await api.get_objects()
    if success:
        logging.info(f"Retrieved objects: {len(response)} items")
        logging.info(f"Sample data: {response[0]}")
    else:
        logging.error(f"Failed to retrieve objects: {response}")
    await asyncio.sleep(2)  # Wait for connection test to complete
    success, response = await api.get_locations()
    if success:
        logging.info(f"Retrieved locations: {len(response)} items")
        logging.info(f"Sample data: {response}")
    else:
        logging.error(f"Failed to retrieve locations: {response}")


if __name__ == "__main__":
    asyncio.run(main())
