from smartx_rfid.api.xtrack import ApiXtrack
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
xtrack = ApiXtrack("http://shopee2.smtx.com.br:6124/req")


async def main():
    success, data = await xtrack.get_identifications()
    if success:
        logging.info(f"Identifications: {data[:10]}")
    else:
        logging.error(f"Failed to get identifications: {data}")


if __name__ == "__main__":
    asyncio.run(main())
