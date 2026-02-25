import logging
from smartx_rfid.api.omie import ApiOmie
import asyncio

logging.basicConfig(level=logging.INFO)

omie = ApiOmie(
    app_key="1318987347678",
    app_secret="8b7293a77ae7773a5e9e638f5af46fd2",
)


async def main():
    omie_orders = await omie.get_all_orders()
    orders = omie_orders.get("orders", [])
    logging.info(f"Total orders fetched: {len(orders)}")
    logging.info("Sample order data:")
    logging.info(orders[0].keys() if orders else "No orders found")
    logging.info(orders[:5])


asyncio.run(main())
