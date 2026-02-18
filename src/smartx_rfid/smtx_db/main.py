import logging
from smartx_rfid.db._main import DatabaseManager
from .encode_helpers import parse_encode_rule, build_epc

connection_string_example = "mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx"


class SmtxDb:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.db_manager = DatabaseManager(self.connection_string)
        self.db_manager.initialize()

    def get_customer_ids(self, limit: int | None = None):
        query = "SELECT * FROM customer"
        if limit is not None:
            query += f" LIMIT {limit}"
        return self.db_manager.execute_query(query)

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
