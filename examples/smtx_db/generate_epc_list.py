from smartx_rfid.smtx_db import SmtxDb, connection_string_example
from smartx_rfid.smtx_db.encode_helpers import data_to_hex
import logging

logging.basicConfig(level=logging.INFO)

PRODUCTION_ORDER_ID = 322

logging.info("Initializing SmtxDb with connection string.")
smtx_db = SmtxDb(connection_string_example)
logging.info("SmtxDb initialized successfully.")

epc_list = smtx_db.generate_epc_list(10, PRODUCTION_ORDER_ID)
logging.info(f"Generated EPC list: {epc_list}")

logging.info("Converting EPCs to hex format.")
hex_epc = data_to_hex("118864")
logging.info(f"Hexadecimal representation of '118864': {hex_epc}")
