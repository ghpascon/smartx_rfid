from smartx_rfid.clients.id_logistic import IdLogisticClient
import logging

logging.basicConfig(level=logging.INFO)

# UTILS
current_gtins = {"07300230759482": 5, "07300234038545": 3, "789": 2, "ABC": 4}


client = IdLogisticClient(
    url="mysql+pymysql://{user}:{password}@localhost:3306/idl",
    user="root",
    password="admin",
)

# positions
success, positions = client.get_positions_by_user("pendente")
if not success:
    logging.error(f"Failed to get positions: {positions}")
    exit(1)

success, eans = client.get_eans_on_support(list(positions.keys())[0])
if success:
    logging.info(f"EANs on support: {eans}")
else:
    logging.error(f"Failed to get EANs on support: {eans}")
    exit(1)

data = client.compare_gtins_support_data(eans, current_gtins.copy())

logging.info(f"Comparison data: {data}")

# # SUPORTE
success, supconf_data = client.get_data_supconf("1408380")
if success:
    logging.info(f"Supconf data: {supconf_data}")
else:
    logging.error(f"Failed to get supconf data: {supconf_data}")
    exit(1)

data = client.compare_gtins_support_data(supconf_data, current_gtins.copy())
logging.info(f"Comparison data: {data}")
