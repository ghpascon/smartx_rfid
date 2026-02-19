from smartx_rfid.smtx_db import SmtxDb
import logging

logging.basicConfig(level=logging.INFO)

logging.info("Initializing SmtxDb with connection string.")
smtx_db = SmtxDb("mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx_teste")
logging.info("SmtxDb initialized successfully.")

results = smtx_db.get_customer_ids(10)
logging.info(f"Customer IDs Results: {results}")

client_id = int(input("Enter client_id to fetch orders: "))
orders = smtx_db.get_orders(client_id)
logging.info(f"Orders for client_id {client_id}: {orders}")

order_id = int(input("Enter order_id to fetch batches: "))
batches = smtx_db.get_batches(order_id)
logging.info(f"Batches for order_id {order_id}: {batches}")

encode_rule = smtx_db.get_encode_rule()
logging.info(f"Encode Rule: {encode_rule}")
