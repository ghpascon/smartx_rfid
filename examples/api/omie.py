import logging
from smartx_rfid.api.omie import ApiOmie

logging.basicConfig(level=logging.INFO)

omie = ApiOmie(
    app_key="1318987347678",
    app_secret="8b7293a77ae7773a5e9e638f5af46fd2",
)

if __name__ == "__main__":
    logging.info("Fetching all products from Omie...")
    produtos = omie.get_all_products(per_page=100)
    logging.info(f"Total products fetched: {len(produtos)}")
    logging.info("Sample product data:")
    logging.info([p for p in produtos if not p.get("codigo").startswith("R00")])  # Log the first 10 products

    logging.info("Fetching all clients from Omie...")
    clientes = omie.get_all_clients()
    logging.info(f"Total clients fetched: {len(clientes)}")

    logging.info("Sample client data:")
    logging.info(clientes[:10])
