from smartx_rfid.api.xtrack import ApiXtrack
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
xtrack = ApiXtrack("https://demo.smtx.com.br:6100/req")


async def main():
    success, data = await xtrack.move_object("00003807", "portal1")
    if success:
        logging.info(f"Move object response: {data}")
    else:
        logging.error(f"Failed to move object: {data}")


if __name__ == "__main__":
    asyncio.run(main())
