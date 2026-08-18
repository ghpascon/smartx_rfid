from smartx_rfid.clients.toolsort import ToolSortClient
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

client = ToolSortClient(url="https://hapiapp.toolsort.com.br", username="smartx", password="5c1EGxL1#")


async def main():
    # client = ToolSortClient(url="https://hapiapp.toolsort.com.br", username="username", password="password")
    data = await client.verify_card("3529903170")  # Replace with a valid card ID for testing
    logging.info(f"Verified card response: {data}")
    # descriptions = await client.get_descriptions(
    #     ["e00000000000e00000000669"]
    # )  # Replace with a valid EPC list for testing
    # logging.info(f"Get descriptions response: {descriptions}")


asyncio.run(main())
