import logging
from smartx_rfid.db._main import DatabaseManager
from .encode_helpers import parse_encode_rule, build_epc
from smartx_rfid.models.products import ProductsType, ProductsOrders, ReadersType, Readers, Customer
from datetime import datetime

connection_string_example = "mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx"


class SmtxDb:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.db_manager = DatabaseManager(self.connection_string)
        self.db_manager.initialize()

    # [ Customers ]
    def get_customers(self, limit: int | None = None):
        try:
            with self.db_manager.get_session() as session:
                q = session.query(Customer)
                if limit is not None:
                    q = q.limit(limit)
                return [r.to_dict() for r in q.all()]
        except Exception as e:
            logging.error(f"Error fetching customers: {e}")
            return []

    def get_customer(self, client_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(Customer).filter_by(ID=client_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching customer with id {client_id}: {e}")
            return None

    # [ Orders ]
    def get_orders(self, client_id: int):
        query = f"SELECT * FROM production_order WHERE customer_id = {client_id}"
        return self.db_manager.execute_query(query)

    def get_batches(self, order_id: int):
        query = f"SELECT * FROM production_order_batch WHERE production_order_id = {order_id}"
        return self.db_manager.execute_query(query)

    def get_encode_rule(self, rule_id: int | None = None):
        query = "SELECT params FROM enc_rule"
        if rule_id is not None:
            query += f" WHERE id = {rule_id}"
        return self.db_manager.execute_query(query)

    def generate_epc_list(self, qtd: int, order_id: int):
        logging.info(f"Generating EPC list for order_id {order_id} with quantity {qtd}.")

        # Max serial
        max_serial_query = (
            f"SELECT MAX(serial) AS max_serial FROM production_order_tag WHERE production_order_id = {order_id}"
        )
        max_serial_result = self.db_manager.execute_query(max_serial_query)
        logging.info(f"Max serial result: {max_serial_result}")
        max_serial = (
            max_serial_result[0]["max_serial"]
            if max_serial_result and max_serial_result[0]["max_serial"] is not None
            else 0
        )

        # Encoding rule
        encode_rule_query = (
            f"SELECT params FROM enc_rule WHERE id = (SELECT enc_rule_id FROM production_order WHERE id = {order_id})"
        )
        encode_rule_result = self.db_manager.execute_query(encode_rule_query)
        logging.info(f"Encode rule result: {encode_rule_result}")

        if not encode_rule_result:
            raise ValueError(f"No encode rule found for order_id {order_id}")

        rule = parse_encode_rule(encode_rule_result[0]["params"])
        logging.info(f"Parsed encode rule: {rule}")

        epc_list = [build_epc(max_serial + i, rule) for i in range(1, qtd + 1)]
        logging.info(f"Generated {len(epc_list)} EPCs starting from serial {max_serial + 1}.")
        return epc_list

    # [ Products ]
    # Product Types
    def get_product_types(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(ProductsType).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logging.error(f"Error fetching product types: {e}")
            return []

    def get_product_type(self, product_type_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(ProductsType).filter_by(id=product_type_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching product type with id {product_type_id}: {e}")
            return None

    def add_product_type(self, name: str, description: str | None = None):
        try:
            with self.db_manager.get_session() as session:
                product_type = ProductsType(name=name, description=description)
                session.add(product_type)
                session.flush()  # Ensure ID is generated
                return True, product_type.id
        except Exception as e:
            logging.error(f"Error adding product type: {e}")
            return False, None

    def update_product_type(self, product_type_id: int, name: str | None = None, description: str | None = None):
        try:
            with self.db_manager.get_session() as session:
                product_type = session.query(ProductsType).filter_by(id=product_type_id).first()
                if not product_type:
                    return False, f"ProductType with id {product_type_id} not found"
                if name is not None:
                    product_type.name = name
                if description is not None:
                    product_type.description = description
        except Exception as e:
            logging.error(f"Error updating product type: {e}")
            return False, str(e)
        return True, None

    def delete_product_type(self, product_type_id: int):
        try:
            with self.db_manager.get_session() as session:
                product_type = session.query(ProductsType).filter_by(id=product_type_id).first()
                if not product_type:
                    return False, f"ProductType with id {product_type_id} not found"
                session.delete(product_type)
        except Exception as e:
            logging.error(f"Error deleting product type: {e}")
            return False, str(e)
        return True, None

    # Readers Type
    def get_reader_types(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(ReadersType).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logging.error(f"Error fetching readers type: {e}")
            return []

    def get_reader_type(self, reader_type_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(ReadersType).filter_by(id=reader_type_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching reader type with id {reader_type_id}: {e}")
            return None

    def add_reader_type(self, name: str, description: str | None = None):
        try:
            with self.db_manager.get_session() as session:
                reader_type = ReadersType(name=name, description=description)
                session.add(reader_type)
                session.flush()  # Ensure ID is generated
                return True, reader_type.id
        except Exception as e:
            logging.error(f"Error adding reader type: {e}")
            return False, None

    def update_reader_type(self, reader_type_id: int, name: str | None = None, description: str | None = None):
        try:
            with self.db_manager.get_session() as session:
                reader_type = session.query(ReadersType).filter_by(id=reader_type_id).first()
                if not reader_type:
                    return False, f"ReaderType with id {reader_type_id} not found"
                if name is not None:
                    reader_type.name = name
                if description is not None:
                    reader_type.description = description
        except Exception as e:
            logging.error(f"Error updating reader type: {e}")
            return False, str(e)
        return True, None

    def delete_reader_type(self, reader_type_id: int):
        try:
            with self.db_manager.get_session() as session:
                reader_type = session.query(ReadersType).filter_by(id=reader_type_id).first()
                if not reader_type:
                    return False, f"ReaderType with id {reader_type_id} not found"
                session.delete(reader_type)
        except Exception as e:
            logging.error(f"Error deleting reader type: {e}")
            return False, str(e)
        return True, None

    def add_reader(self, reader_type_id: int, serial_number: str, hostname: str | None = None):
        try:
            with self.db_manager.get_session() as session:
                if not session.query(ReadersType).filter_by(id=reader_type_id).first():
                    return False, f"ReaderType with id {reader_type_id} not found"
                reader = Readers(reader_type_id=reader_type_id, serial_number=serial_number, hostname=hostname)
                session.add(reader)
                session.flush()  # Ensure ID is generated
                return True, reader.id
        except Exception as e:
            logging.error(f"Error adding reader: {e}")
            return False, None

    def get_readers(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(Readers).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logging.error(f"Error fetching readers: {e}")
            return []

    def get_available_readers(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(Readers).filter_by(available=True).all()
                return [r.id for r in results]
        except Exception as e:
            logging.error(f"Error fetching available readers: {e}")
            return []

    def get_reader(self, reader_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(Readers).filter_by(id=reader_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching reader with id {reader_id}: {e}")
            return None

    def update_reader(
        self,
        reader_id: int,
        reader_type_id: int | None = None,
        serial_number: str | None = None,
        hostname: str | None = None,
        available: bool | None = None,
    ):
        try:
            with self.db_manager.get_session() as session:
                reader = session.query(Readers).filter_by(id=reader_id).first()
                if not reader:
                    return False, f"Reader with id {reader_id} not found"
                if reader_type_id is not None:
                    if not session.query(ReadersType).filter_by(id=reader_type_id).first():
                        return False, f"ReaderType with id {reader_type_id} not found"
                    reader.reader_type_id = reader_type_id
                if serial_number is not None:
                    reader.serial_number = serial_number
                if hostname is not None:
                    reader.hostname = hostname
                if available is not None:
                    reader.available = available
        except Exception as e:
            logging.error(f"Error updating reader: {e}")
            return False, str(e)
        return True, None

    def delete_reader(self, reader_id: int):
        try:
            with self.db_manager.get_session() as session:
                reader = session.query(Readers).filter_by(id=reader_id).first()
                if not reader:
                    return False, f"Reader with id {reader_id} not found"
                in_use = session.query(ProductsOrders).filter_by(reader_id=reader_id).first()
                if in_use:
                    return False, f"Reader with id {reader_id} is in use by a product order"
                session.delete(reader)
        except Exception as e:
            logging.error(f"Error deleting reader: {e}")
            return False, str(e)
        return True, None

    def get_decoded_readers(self):
        try:
            with self.db_manager.get_session() as session:
                results = (
                    session.query(Readers, ReadersType.name.label("reader_type_name"))
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .all()
                )
                decoded = []
                for reader, reader_type_name in results:
                    d = reader.to_dict()
                    d["reader_type_name"] = reader_type_name
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching decoded readers: {e}")
            return []

    def get_decoded_reader(self, reader_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = (
                    session.query(Readers, ReadersType.name.label("reader_type_name"))
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .filter(Readers.id == reader_id)
                    .first()
                )
                if not result:
                    return None
                reader, reader_type_name = result
                d = reader.to_dict()
                d["reader_type_name"] = reader_type_name
                return d
        except Exception as e:
            logging.error(f"Error fetching decoded reader with id {reader_id}: {e}")
            return None

    def get_decoded_readers_by_ids(self, reader_ids: list[int]):
        try:
            with self.db_manager.get_session() as session:
                results = (
                    session.query(Readers, ReadersType.name.label("reader_type_name"))
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .filter(Readers.id.in_(reader_ids))
                    .all()
                )
                decoded = []
                for reader, reader_type_name in results:
                    d = reader.to_dict()
                    d["reader_type_name"] = reader_type_name
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching decoded readers by ids {reader_ids}: {e}")
            return []

    # Product Orders
    def get_product_orders(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(ProductsOrders).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logging.error(f"Error fetching product orders: {e}")
            return []

    def get_product_order(self, order_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(ProductsOrders).filter_by(id=order_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching product order with id {order_id}: {e}")
            return None

    def get_product_orders_by_client(self, client_id: int):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(ProductsOrders).filter_by(client_id=client_id).all()
                return [r.id for r in results]
        except Exception as e:
            logging.error(f"Error fetching product orders for client_id {client_id}: {e}")
            return []

    def get_product_orders_by_product_type(self, product_type_id: int):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(ProductsOrders).filter_by(product_type_id=product_type_id).all()
                return [r.id for r in results]
        except Exception as e:
            logging.error(f"Error fetching product orders for product_type_id {product_type_id}: {e}")
            return []

    def get_product_orders_by_date(self, start_date: datetime, end_date: datetime):
        try:
            with self.db_manager.get_session() as session:
                results = (
                    session.query(ProductsOrders)
                    .filter(ProductsOrders.created_at >= start_date, ProductsOrders.created_at <= end_date)
                    .all()
                )
                return [r.id for r in results]
        except Exception as e:
            logging.error(f"Error fetching product orders between {start_date} and {end_date}: {e}")
            return []

    def add_product_order(self, product_type_id: int, client_id: int, reader_id: int | None, version: str):
        try:
            with self.db_manager.get_session() as session:
                # Validate product_type_id
                if not session.query(ProductsType).filter_by(id=product_type_id).first():
                    return False, f"ProductType with id {product_type_id} not found"

                # Validate client_id
                if not session.query(Customer).filter_by(ID=client_id).first():
                    return False, f"Customer with id {client_id} not found"

                # Validate reader_id and check availability
                if reader_id is not None:
                    reader = session.query(Readers).filter_by(id=reader_id).first()
                    if not reader:
                        return False, f"Reader with id {reader_id} not found"
                    if not reader.available:
                        return False, f"Reader with id {reader_id} is not available"

                product_order = ProductsOrders(
                    product_type_id=product_type_id, client_id=client_id, reader_id=reader_id, version=version
                )
                session.add(product_order)
                if reader_id is not None:
                    reader.available = False
                session.flush()  # Ensure ID is generated
                return True, product_order.id
        except Exception as e:
            logging.error(f"Error adding product order: {e}")
            return False, None

    def update_product_order(self, order_id: int, **kwargs):
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(ProductsOrders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"ProductsOrders with id {order_id} not found"
                for key, value in kwargs.items():
                    if hasattr(product_order, key):
                        setattr(product_order, key, value)
        except Exception as e:
            logging.error(f"Error updating product order: {e}")
            return False, str(e)
        return True, None

    def delete_product_order(self, order_id: int):
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(ProductsOrders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"ProductsOrders with id {order_id} not found"
                # Restore reader availability
                reader = session.query(Readers).filter_by(id=product_order.reader_id).first()
                if reader:
                    reader.available = True
                session.delete(product_order)
        except Exception as e:
            logging.error(f"Error deleting product order: {e}")
            return False, str(e)
        return True, None

    def add_reader_to_product_order(self, order_id: int, reader_id: int):
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(ProductsOrders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"ProductsOrders with id {order_id} not found"

                if product_order.reader_id is not None:
                    return False, f"ProductsOrders with id {order_id} already has a reader assigned"

                reader = session.query(Readers).filter_by(id=reader_id).first()
                if not reader:
                    return False, f"Reader with id {reader_id} not found"
                if not reader.available:
                    return False, f"Reader with id {reader_id} is not available"

                product_order.reader_id = reader_id
                reader.available = False
        except Exception as e:
            logging.error(f"Error adding reader to product order: {e}")
            return False, str(e)
        return True, None

    # [ Product Orders Workflow ]
    def product_order_mount(self, order_id: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"ProductsOrders with id {order_id} not found"
        if order.get("reader_id") is None:
            return False, "Order must have a reader assigned before mounting"
        if order.get("mounted_at") is not None:
            return False, "Order already mounted"
        return self.update_product_order(order_id, mounted_at=datetime.now())

    def product_order_test(self, order_id: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"ProductsOrders with id {order_id} not found"
        if order.get("mounted_at") is None:
            return False, "Order must be mounted before testing"
        if order.get("tested_at") is not None:
            return False, "Order already tested"
        return self.update_product_order(order_id, tested_at=datetime.now())

    def product_order_ship(self, order_id: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"ProductsOrders with id {order_id} not found"
        if order.get("tested_at") is None:
            return False, "Order must be tested before shipping"
        if order.get("shipped_at") is not None:
            return False, "Order already shipped"
        return self.update_product_order(order_id, shipped_at=datetime.now())

    def product_order_activate(self, order_id: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"ProductsOrders with id {order_id} not found"
        if order.get("shipped_at") is None:
            return False, "Order must be shipped before activation"
        if order.get("activated_at") is not None:
            return False, "Order already activated"
        return self.update_product_order(order_id, activated_at=datetime.now())

    # [ DECODED ]
    def get_decoded_orders(self):
        try:
            with self.db_manager.get_session() as session:
                results = (
                    session.query(
                        ProductsOrders,
                        ProductsType.name.label("product_type_name"),
                        Customer.NAME.label("client_name"),
                        Readers.serial_number.label("reader_serial"),
                        Readers.hostname.label("reader_hostname"),
                        ReadersType.name.label("reader_type_name"),
                    )
                    .join(ProductsType, ProductsOrders.product_type_id == ProductsType.id)
                    .join(Customer, ProductsOrders.client_id == Customer.ID)
                    .join(Readers, ProductsOrders.reader_id == Readers.id)
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .all()
                )
                decoded = []
                for order, product_type_name, client_name, reader_serial, reader_hostname, reader_type_name in results:
                    d = order.to_dict()
                    d["product_type_name"] = product_type_name
                    d["client_name"] = client_name
                    d["reader_serial"] = reader_serial
                    d["reader_hostname"] = reader_hostname
                    d["reader_type_name"] = reader_type_name
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching decoded orders: {e}")
            return []

    def get_decoded_order(self, order_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = (
                    session.query(
                        ProductsOrders,
                        ProductsType.name.label("product_type_name"),
                        Customer.NAME.label("client_name"),
                        Readers.serial_number.label("reader_serial"),
                        Readers.hostname.label("reader_hostname"),
                        ReadersType.name.label("reader_type_name"),
                    )
                    .join(ProductsType, ProductsOrders.product_type_id == ProductsType.id)
                    .join(Customer, ProductsOrders.client_id == Customer.ID)
                    .join(Readers, ProductsOrders.reader_id == Readers.id)
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .filter(ProductsOrders.id == order_id)
                    .first()
                )
                if not result:
                    return None
                order, product_type_name, client_name, reader_serial, reader_hostname, reader_type_name = result
                d = order.to_dict()
                d["product_type_name"] = product_type_name
                d["client_name"] = client_name
                d["reader_serial"] = reader_serial
                d["reader_hostname"] = reader_hostname
                d["reader_type_name"] = reader_type_name
                return d
        except Exception as e:
            logging.error(f"Error fetching decoded order with id {order_id}: {e}")
            return None

    def get_decoded_orders_by_ids(self, order_ids: list[int]):
        try:
            with self.db_manager.get_session() as session:
                results = (
                    session.query(
                        ProductsOrders,
                        ProductsType.name.label("product_type_name"),
                        Customer.NAME.label("client_name"),
                        Readers.serial_number.label("reader_serial"),
                        Readers.hostname.label("reader_hostname"),
                        ReadersType.name.label("reader_type_name"),
                    )
                    .join(ProductsType, ProductsOrders.product_type_id == ProductsType.id)
                    .join(Customer, ProductsOrders.client_id == Customer.ID)
                    .join(Readers, ProductsOrders.reader_id == Readers.id)
                    .join(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .filter(ProductsOrders.id.in_(order_ids))
                    .all()
                )
                decoded = []
                for order, product_type_name, client_name, reader_serial, reader_hostname, reader_type_name in results:
                    d = order.to_dict()
                    d["product_type_name"] = product_type_name
                    d["client_name"] = client_name
                    d["reader_serial"] = reader_serial
                    d["reader_hostname"] = reader_hostname
                    d["reader_type_name"] = reader_type_name
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching decoded orders by ids {order_ids}: {e}")
            return []
