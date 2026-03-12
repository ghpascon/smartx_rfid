from smartx_rfid.smtx_db import SmtxDb
from smartx_rfid.models.products import ProductsType, ReadersType
import logging

logging.basicConfig(level=logging.INFO)

logging.info("Initializing SmtxDb with connection string.")
smtx_db = SmtxDb("mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx_teste")
smtx_db.db_manager.register_models(ProductsType, ReadersType)
smtx_db.db_manager.create_tables()

# [Products]
# Create
success, product_type_id = smtx_db.add_product_type(
    name="New Product Type", description="Description of new product type"
)
logging.info(f"Product type created: success={success}, id={product_type_id}")
# Retrieve
product_types = smtx_db.get_product_types()
logging.info(f"Retrieved product types: {product_types}")

# Update
success, error = smtx_db.update_product_type(
    product_type_id, name="Updated Product Type", description="Updated description"
)
if success:
    logging.info(f"Product type with id {product_type_id} updated successfully.")
else:
    logging.error(f"Error updating product type: {error}")
# Retrieve again to confirm update
product_types = smtx_db.get_product_types()
logging.info(f"Retrieved product types after update: {product_types}")
# Delete
_ = input("Press Enter to delete the product type...")
success, error = smtx_db.delete_product_type(product_type_id)
if success:
    logging.info(f"Product type with id {product_type_id} deleted successfully.")
else:
    logging.error(f"Error deleting product type: {error}")
# Retrieve again to confirm deletion
product_types = smtx_db.get_product_types()
logging.info(f"Retrieved product types after deletion: {product_types}")

# [ReadersType]
# Create
success, reader_type_id = smtx_db.add_reader_type(name="New Reader Type", description="Description of new reader type")
logging.info(f"Reader type created: success={success}, id={reader_type_id}")
# Retrieve
reader_types = smtx_db.get_reader_types()
logging.info(f"Retrieved reader types: {reader_types}")
# Update
success, error = smtx_db.update_reader_type(
    reader_type_id, name="Updated Reader Type", description="Updated description"
)
if success:
    logging.info(f"Reader type with id {reader_type_id} updated successfully.")
else:
    logging.error(f"Error updating reader type: {error}")
# Retrieve again to confirm update
reader_types = smtx_db.get_reader_types()
logging.info(f"Retrieved reader types after update: {reader_types}")
# Delete
_ = input("Press Enter to delete the reader type...")
success, error = smtx_db.delete_reader_type(reader_type_id)
if success:
    logging.info(f"Reader type with id {reader_type_id} deleted successfully.")
else:
    logging.error(f"Error deleting reader type: {error}")
