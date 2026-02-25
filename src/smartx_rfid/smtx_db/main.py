import logging
from sqlalchemy.orm import aliased
from smartx_rfid.db._main import DatabaseManager
from smartx_rfid.models.orders import ReadersType, Readers, Orders
from datetime import datetime
from smartx_rfid.models.users import Users

connection_string_example = "mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx"


class SmtxDb:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.db_manager = DatabaseManager(self.connection_string)
        self.db_manager.initialize()

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
        logging.info(f"Adding reader type: name={name}, description={description}")
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
        logging.info(f"Updating reader type id={reader_type_id}, name={name}, description={description}")
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

    # Readers
    def add_reader(self, reader_type_id: int, serial_number: str, hostname: str | None = None):
        logging.info(
            f"Adding reader: reader_type_id={reader_type_id}, serial_number={serial_number}, hostname={hostname}"
        )
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

    def get_readers(self, filters: dict | None = None):
        try:
            with self.db_manager.get_session() as session:
                query = session.query(Readers, ReadersType.name.label("reader_type_name")).outerjoin(
                    ReadersType, Readers.reader_type_id == ReadersType.id
                )

                # Apply filters if provided
                if filters:
                    for field, value in filters.items():
                        if hasattr(Readers, field):
                            query = query.filter(getattr(Readers, field) == value)
                        elif hasattr(ReadersType, field):
                            query = query.filter(getattr(ReadersType, field) == value)
                        else:
                            logging.warning(f"Unknown filter field: {field}")

                results = query.all()
                decoded = []
                for reader, reader_type_name in results:
                    d = reader.to_dict()
                    d["reader_type_name"] = reader_type_name
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching readers: {e}")
            return []

    def get_available_readers(self):
        readers = self.get_readers(filters={"available": True})
        return readers

    def get_readers_by_type(self, reader_type_id: int):
        readers = self.get_readers(filters={"reader_type_id": reader_type_id})
        return readers

    def get_readers_by_type_name(self, type_name: str):
        readers = self.get_readers(filters={"name": type_name})
        return readers

    def get_readers_by_availability(self, available: bool):
        readers = self.get_readers(filters={"available": available})
        return readers

    def get_reader(self, reader_id: int):
        readers = self.get_readers(filters={"id": reader_id})
        return readers[0] if readers else None

    def get_reader_by_hostname(self, hostname: str):
        readers = self.get_readers(filters={"hostname": hostname})
        return readers[0] if readers else None

    def get_reader_by_ids(self, reader_ids: list):
        readers = self.get_readers(filters={"id": reader_ids})
        return readers

    def get_reader_by_serial(self, serial_number: str):
        readers = self.get_readers(filters={"serial_number": serial_number})
        return readers[0] if readers else None

    def update_reader(
        self,
        reader_id: int,
        reader_type_id: int | None = None,
        serial_number: str | None = None,
        hostname: str | None = None,
        available: bool | None = None,
    ):
        logging.info(
            f"Updating reader id={reader_id}, reader_type_id={reader_type_id}, serial_number={serial_number}, hostname={hostname}, available={available}"
        )
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
                in_use = session.query(Orders).filter_by(reader_id=reader_id).first()
                if in_use:
                    return False, f"Reader with id {reader_id} is in use by a product order"
                session.delete(reader)
        except Exception as e:
            logging.error(f"Error deleting reader: {e}")
            return False, str(e)
        return True, None

    # Product Orders
    def get_product_orders(self, filters: dict | None = None):
        """
        Busca pedidos de produto, aceitando filtros de igualdade e de intervalo (__gte, __lte).
        """
        try:
            with self.db_manager.get_session() as session:
                CreatedBy = aliased(Users)
                MountedBy = aliased(Users)
                TestedBy = aliased(Users)
                ShippedBy = aliased(Users)
                ActivatedBy = aliased(Users)

                query = (
                    session.query(
                        Orders,
                        Readers.serial_number.label("reader_serial"),
                        Readers.hostname.label("reader_hostname"),
                        ReadersType.name.label("reader_type_name"),
                        CreatedBy.username.label("created_by_username"),
                        MountedBy.username.label("mounted_by_username"),
                        TestedBy.username.label("tested_by_username"),
                        ShippedBy.username.label("shipped_by_username"),
                        ActivatedBy.username.label("activated_by_username"),
                    )
                    .outerjoin(Readers, Orders.reader_id == Readers.id)
                    .outerjoin(ReadersType, Readers.reader_type_id == ReadersType.id)
                    .outerjoin(CreatedBy, Orders.created_by == CreatedBy.id)
                    .outerjoin(MountedBy, Orders.mounted_by == MountedBy.id)
                    .outerjoin(TestedBy, Orders.tested_by == TestedBy.id)
                    .outerjoin(ShippedBy, Orders.shipped_by == ShippedBy.id)
                    .outerjoin(ActivatedBy, Orders.activated_by == ActivatedBy.id)
                )

                # Aplica filtros de igualdade e de intervalo
                if filters:
                    for field, value in filters.items():
                        if "__gte" in field:
                            base_field = field.replace("__gte", "")
                            if hasattr(Orders, base_field):
                                query = query.filter(getattr(Orders, base_field) >= value)
                        elif "__lte" in field:
                            base_field = field.replace("__lte", "")
                            if hasattr(Orders, base_field):
                                query = query.filter(getattr(Orders, base_field) <= value)
                        elif hasattr(Orders, field):
                            query = query.filter(getattr(Orders, field) == value)
                        elif hasattr(Readers, field):
                            query = query.filter(getattr(Readers, field) == value)
                        elif hasattr(ReadersType, field):
                            query = query.filter(getattr(ReadersType, field) == value)
                        else:
                            logging.warning(f"Unknown filter field: {field}")

                results = query.all()
                decoded = []
                for (
                    order,
                    reader_serial,
                    reader_hostname,
                    reader_type_name,
                    created_by_username,
                    mounted_by_username,
                    tested_by_username,
                    shipped_by_username,
                    activated_by_username,
                ) in results:
                    d = order.to_dict()
                    d["reader_serial"] = reader_serial
                    d["reader_hostname"] = reader_hostname
                    d["reader_type_name"] = reader_type_name
                    d["created_by_username"] = created_by_username
                    d["mounted_by_username"] = mounted_by_username
                    d["tested_by_username"] = tested_by_username
                    d["shipped_by_username"] = shipped_by_username
                    d["activated_by_username"] = activated_by_username
                    decoded.append(d)
                return decoded
        except Exception as e:
            logging.error(f"Error fetching product orders: {e}")
            return []

    def get_product_order(self, order_id: int):
        order = self.get_product_orders(filters={"id": order_id})
        return order[0] if order else None

    def get_product_orders_by_ids(self, order_ids: list):
        orders = self.get_product_orders(filters={"id": order_ids})
        return orders

    def get_product_orders_by_client(self, client: str):
        orders = self.get_product_orders(filters={"client_name": client})
        return orders

    def get_product_orders_by_cnpj(self, cnpj: str):
        orders = self.get_product_orders(filters={"client_cnpj": cnpj})
        return orders

    def get_product_orders_by_product_code(self, product_code: str):
        orders = self.get_product_orders(filters={"product_code": product_code})
        return orders

    def get_product_orders_by_order_number(self, order_number: int):
        orders = self.get_product_orders(filters={"order_number": order_number})
        return orders

    def get_product_orders_by_date(self, start_date: datetime, end_date: datetime, field: str = "created_at"):
        if getattr(Orders, field, None) is None:
            logging.error(f"Invalid field '{field}' for date filtering in Orders")
            return []
        filters = {f"{field}__gte": start_date, f"{field}__lte": end_date}
        try:
            return self.get_product_orders(filters)
        except Exception as e:
            logging.error(f"Error fetching product orders between {start_date} and {end_date}: {e}")
            return []

    def get_product_orders_by_reader_type(self, reader_type_id: int):
        return self.get_product_orders(filters={"reader_type_id": reader_type_id})

    def get_product_orders_by_reader_type_name(self, reader_type_name: str):
        type_id = self.get_reader_types()
        type_id = next((t.get("id") for t in type_id if t.get("name") == reader_type_name), None)
        if type_id is None:
            return []
        return self.get_product_orders(filters={"reader_type_id": type_id})

    def get_product_orders_by_reader(self, reader_id: int):
        orders = self.get_product_orders(filters={"reader_id": reader_id})
        return orders

    def add_product_order(
        self,
        order_number: int,
        client_name: str,
        client_cnpj: str | None,
        product_code: str,
        product_description: str | None,
        product_family: str | None,
        reader_id: int | None = None,
        created_by: int | None = None,
    ):
        logging.info(
            f"Adding product order: order_number={order_number}, client_name={client_name}, product_code={product_code}, reader_id={reader_id}, created_by={created_by}"
        )
        try:
            with self.db_manager.get_session() as session:
                # Validate created_by user exists
                if created_by is not None:
                    if not session.query(Users).filter_by(id=created_by).first():
                        return False, f"User with id {created_by} not found"

                # Validate reader_id and check availability
                if reader_id is not None:
                    reader = session.query(Readers).filter_by(id=reader_id).first()
                    if not reader:
                        return False, f"Reader with id {reader_id} not found"
                    if not reader.available:
                        return False, f"Reader with id {reader_id} is not available"

                product_order = Orders(
                    order_number=order_number,
                    client_name=client_name,
                    client_cnpj=client_cnpj,
                    product_code=product_code,
                    product_description=product_description,
                    product_family=product_family,
                    reader_id=reader_id,
                    created_by=created_by,
                )
                session.add(product_order)
                if reader_id is not None:
                    reader.available = False
                session.flush()  # Ensure ID is generated
                return True, product_order.id
        except Exception as e:
            logging.error(f"Error adding product order: {e}")
            return False, str(e)

    def update_product_order(self, order_id: int, **kwargs):
        logging.info(f"Updating product order id={order_id}, updates={kwargs}")
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(Orders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"Orders with id {order_id} not found"
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
                product_order = session.query(Orders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"Orders with id {order_id} not found"
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
        logging.info(f"Adding reader id={reader_id} to product order id={order_id}")
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(Orders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"Orders with id {order_id} not found"

                reader = session.query(Readers).filter_by(id=reader_id).first()
                if not reader:
                    return False, f"Reader with id {reader_id} not found"
                if not reader.available:
                    return False, f"Reader with id {reader_id} is not available"

                # Free previous reader if any
                if product_order.reader_id:
                    old_reader = session.query(Readers).filter_by(id=product_order.reader_id).first()
                    if old_reader:
                        old_reader.available = True

                product_order.reader_id = reader_id
                reader.available = False
        except Exception as e:
            logging.error(f"Error adding reader to product order: {e}")
            return False, str(e)
        return True, None

    def add_comment_to_product_order(self, order_id: int, comment: str, user: str | None = None):
        if user is None:
            user = "Unknown"
        comment = f"{datetime.now().isoformat()} - {user}: {comment}"
        logging.info(f"Adding comment to product order id={order_id}: {comment}")
        try:
            with self.db_manager.get_session() as session:
                product_order = session.query(Orders).filter_by(id=order_id).first()
                if not product_order:
                    return False, f"Orders with id {order_id} not found"
                existing_comments = product_order.comments or ""
                updated_comments = existing_comments + "\n" + comment if existing_comments else comment
                product_order.comments = updated_comments
        except Exception as e:
            logging.error(f"Error adding comment to product order: {e}")
            return False, str(e)
        return True, comment

    # [ Product Orders Workflow ]
    def product_order_mount(self, order_id: int, mounted_by: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"Orders with id {order_id} not found"
        if order.get("reader_id") is None:
            return False, "Order must have a reader assigned before mounting"
        if order.get("mounted_at") is not None:
            return False, "Order already mounted"
        return self.update_product_order(order_id, mounted_at=datetime.now(), mounted_by=mounted_by)

    def product_order_test(self, order_id: int, tested_by: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"Orders with id {order_id} not found"
        if order.get("mounted_at") is None:
            return False, "Order must be mounted before testing"
        if order.get("tested_at") is not None:
            return False, "Order already tested"
        return self.update_product_order(order_id, tested_at=datetime.now(), tested_by=tested_by)

    def product_order_ship(self, order_id: int, shipped_by: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"Orders with id {order_id} not found"
        if order.get("tested_at") is None:
            return False, "Order must be tested before shipping"
        if order.get("shipped_at") is not None:
            return False, "Order already shipped"
        return self.update_product_order(order_id, shipped_at=datetime.now(), shipped_by=shipped_by)

    def product_order_activate(self, order_id: int, activated_by: int):
        order = self.get_product_order(order_id)
        if not order:
            return False, f"Orders with id {order_id} not found"
        if order.get("shipped_at") is None:
            return False, "Order must be shipped before activation"
        if order.get("activated_at") is not None:
            return False, "Order already activated"
        return self.update_product_order(order_id, activated_at=datetime.now(), activated_by=activated_by)

    # [ USERS ]
    def get_users(self):
        try:
            with self.db_manager.get_session() as session:
                results = session.query(Users).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logging.error(f"Error fetching users: {e}")
            return []

    def get_user(self, user_id: int):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(Users).filter_by(id=user_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching user with id {user_id}: {e}")
            return None

    def get_user_by_username(self, username: str):
        try:
            with self.db_manager.get_session() as session:
                result = session.query(Users).filter_by(username=username).first()
                return result.to_dict() if result else None
        except Exception as e:
            logging.error(f"Error fetching user with username {username}: {e}")
            return None

    def add_user(self, username: str, password_hash: str, role: str = "user"):
        logging.info(f"Adding user: username={username}, role={role}")
        try:
            with self.db_manager.get_session() as session:
                if session.query(Users).filter_by(username=username).first():
                    return False, f"User with username {username} already exists"
                user = Users(username=username, password_hash=password_hash, role=role)
                session.add(user)
                session.flush()  # Ensure ID is generated
                return True, user.id
        except Exception as e:
            logging.error(f"Error adding user: {e}")
            return False, None

    def update_user(self, user_id: int, **kwargs):
        logging.info(f"Updating user id={user_id}, updates={kwargs}")
        try:
            with self.db_manager.get_session() as session:
                user = session.query(Users).filter_by(id=user_id).first()
                if not user:
                    return False, f"User with id {user_id} not found"
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
        except Exception as e:
            logging.error(f"Error updating user: {e}")
            return False, str(e)
        return True, None

    def delete_user(self, user_id: int):
        try:
            with self.db_manager.get_session() as session:
                user = session.query(Users).filter_by(id=user_id).first()
                if not user:
                    return False, f"User with id {user_id} not found"
                session.delete(user)
        except Exception as e:
            logging.error(f"Error deleting user: {e}")
            return False, str(e)
        return True, None

    def delete_user_by_username(self, username: str):
        try:
            with self.db_manager.get_session() as session:
                user = session.query(Users).filter_by(username=username).first()
                if not user:
                    return False, f"User with username {username} not found"
                session.delete(user)
        except Exception as e:
            logging.error(f"Error deleting user by username {username}: {e}")
            return False, str(e)
        return True, None

    # [ UTILS ]
    def _get_column_values(self, model, column_name):
        try:
            with self.db_manager.get_session() as session:
                column = getattr(model, column_name, None)
                if column is None:
                    logging.error(f"Model {model.__name__} does not have column {column_name}")
                    return []
                results = session.query(column).distinct().all()
                return [getattr(r, column_name) for r in results if getattr(r, column_name) is not None]
        except Exception as e:
            logging.error(f"Error fetching column values for {model.__name__}.{column_name}: {e}")
            return []

    def get_customers(self):
        return self._get_column_values(Orders, "client_name")

    def get_cnpjs(self):
        return self._get_column_values(Orders, "client_cnpj")

    def get_orders_numbers(self):
        return self._get_column_values(Orders, "order_number")

    def get_product_codes(self):
        return self._get_column_values(Orders, "product_code")
