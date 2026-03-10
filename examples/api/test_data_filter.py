from smartx_rfid.api.omie import ApiOmie
import os
import logging
from dotenv import load_dotenv
import asyncio

logging.basicConfig(level=logging.INFO)

load_dotenv()

OMIE_APP_KEY = os.getenv("OMIE_APP_KEY")
OMIE_APP_SECRET = os.getenv("OMIE_APP_SECRET")

omie = ApiOmie(
    app_key=OMIE_APP_KEY,
    app_secret=OMIE_APP_SECRET,
)

START_DATE = "01/06/2025"  # Example start date for filtering orders


async def main():
    data = await omie.get_all_orders(start_date=START_DATE)
    if not data.get("success", False):
        logging.error("Failed to fetch orders")
        return
    logging.info(f"Total orders fetched from Omie: {data.get('total_items')}")


if __name__ == "__main__":
    asyncio.run(main())
