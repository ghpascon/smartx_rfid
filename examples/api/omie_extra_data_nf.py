import asyncio
from smartx_rfid.api.omie import ApiOmie
from smartx_rfid.smtx_db import SmtxDb
from smartx_rfid.models.orders import Orders
import logging

logging.basicConfig(level=logging.INFO)

omie = ApiOmie(
    app_key="1318987347678",
    app_secret="8b7293a77ae7773a5e9e638f5af46fd2",
)
smtx_db = SmtxDb("mysql+pymysql://root:admin@localhost:3306/orders")
smtx_db.db_manager.initialize()
smtx_db.db_manager.register_models(Orders)
smtx_db.db_manager.create_tables()


async def main():
    data = await omie.get_all_orders()
    if not data.get("success", False):
        logging.error("Failed to fetch orders")
        return
    omie_orders = data.get("orders", [])
    logging.info(f"Step 1: Total orders fetched from Omie: {data.get('total_items')}")

    # Step 2: Count Omie items by (order_number, product_code, client_name)
    omie_count = {}
    for order in omie_orders:
        key = (order.get("numero_pedido"), order.get("codigo_produto"), order.get("nome_cliente"))
        omie_count[key] = omie_count.get(key, 0) + 1
    logging.info(f"Step 2: Omie item counts: {omie_count}")

    # Step 3: Count DB items by (order_number, product_code, client_name)
    db_orders = smtx_db.get_product_orders()
    db_count = {}
    for order in db_orders:
        key = (order.get("order_number"), order.get("product_code"), order.get("client_name"))
        db_count[key] = db_count.get(key, 0) + 1
    logging.info(f"Step 3: DB item counts: {db_count}")

    # Step 4: For each key, add missing items to DB
    omie_orders_numbers = set()
    inserted_count = 0
    for key, omie_qty in omie_count.items():
        db_qty = db_count.get(key, 0)
        diff = omie_qty - db_qty
        order_number, product_code, client_name = key
        logging.info(f"Step 4: {key} - Omie qty: {omie_qty}, DB qty: {db_qty}, To add: {diff if diff > 0 else 0}")
        if diff > 0:
            # Find Omie orders matching this key
            omie_items = [
                o
                for o in omie_orders
                if (o.get("numero_pedido"), o.get("codigo_produto"), o.get("nome_cliente")) == key
            ]
            # Add only the missing items
            for i in range(db_qty, omie_qty):
                order = omie_items[i]
                logging.info(f"Step 4: Adding product order for {key}")
                result, new_id = smtx_db.add_product_order(
                    order_number=order.get("numero_pedido"),
                    client_name=order.get("nome_cliente"),
                    client_cnpj=order.get("cnpj_cliente"),
                    product_code=order.get("codigo_produto"),
                    product_description=order.get("descricao_produto"),
                    product_family=order.get("familia_produto"),
                )
                logging.info(
                    f"Step 4: Added to database: success={result}, id={new_id}, product={product_code}, client={client_name}"
                )
                inserted_count += 1
                omie_orders_numbers.add(order.get("numero_pedido"))
    logging.info(f"Step 4: Total new items inserted: {inserted_count}")

    # step 5: Add Info to nf
    for order_number in omie_orders_numbers:
        product_orders = smtx_db.get_product_orders_by_order_number(order_number)
        serial_numbers = ",".join(f"{po.get('product_code')}_{po.get('product_serial')}" for po in product_orders)
        success, order_data = await omie.get_order_data(order_number)
        if not success:
            logging.error(f"Step 5: Failed to fetch order data for order {order_number}")
            continue
        if not order_data.get("can_update", False):
            logging.error(f"Step 5: Cannot update order {order_number}")
            continue
        cod_order = order_data.get("cod_order")
        success, response = await omie.add_serial_to_nf(cod_order, serial_numbers)
        if success:
            logging.info(f"Step 5: Added serial numbers to NF for order {order_number}: {serial_numbers}")
        else:
            logging.error(f"Step 5: Failed to add serial numbers to NF for order {order_number}: {response}")


asyncio.run(main())
