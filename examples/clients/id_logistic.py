from smartx_rfid.clients.id_logistic import IdLogisticClient
import logging

logging.basicConfig(level=logging.INFO)

client = IdLogisticClient(
    url="mysql+pymysql://{user}:{password}@localhost:3306/idl",
    user="root",
    password="admin",
)

# # positions
# success, positions = client.get_positions_by_user("pendente")
# if success:
#     logging.info(f'Positions: {positions}')
# else:
#     logging.error(f'Failed to get positions: {positions}')
#     exit(1)

# success, eans = client.get_eans_on_support(list(positions.keys())[0])
# if success:
#     logging.info(f'EANs on support: {eans}')
# else:
#     logging.error(f'Failed to get EANs on support: {eans}')
#     exit(1)

# position_info = {
#     'numinv': '123',
#     'numdoc': '456',
#     'seqdoc': '1',
#     'etadoc': '2024-06-01',
#     'posicao': 'A1'
# }

# comparison = [
#     {'ean': '789', 'descricao': 'Product 1', 'exp_qty': 0, 'read_qty': 8, 'match': '!'},
#     {'ean': '101', 'sku': 'SKU456', 'descricao': 'Product 2', 'exp_qty': 5, 'read_qty': 5, 'match': '='}
# ]

# success, result = client.save_position(position_info, comparison)
# if success:
#     logging.info('Finished position successfully.')
# else:
#     logging.error(f'Failed to finish position: {result}')
#     exit(1)

# # SUPORTE
# success, supconf_data = client.get_data_supconf("1408380")
# if success:
#     logging.info(f'Supconf data: {supconf_data}')
# else:
#     logging.error(f'Failed to get supconf data: {supconf_data}')
#     exit(1)

# success, total = client.get_logconf_status_count(1)
# if success:
#     logging.info(f'Logconf status count: {total}')
# else:
#     logging.error(f'Failed to get logconf status count: {total}')
#     exit(1)

# success, result = client.save_logconf([{
#         'suporte': 'A1',
#         'status': 'OK',
#         'codpro': '12345',
#         'quantidade': 10,
#         'sinal': '=',
#         'qtesperada': 10
#     },
#     {
#         'suporte': 'A1',
#         'status': 'OK',
#         'codpro': '12345',
#         'quantidade': 10,
#         'sinal': '=',
#         'qtesperada': 10
#     },
#     {
#         'suporte': 'A1',
#         'status': 'FALTA',
#         'codpro': '123456',
#         'quantidade': 8,
#         'sinal': '<',
#         'qtesperada': 10
#     }], "logconfdiv")
# if success:
#     logging.info('Saved logconf data successfully.')
# else:
#     logging.error(f'Failed to save logconf data: {result}')
#     exit(1)

# UTILS
current_gtins = {"123": 5, "456": 3, "789": 2, "ABC": 4}
expected_gtins = {
    "123": 5,
    "456": 5,
    "789": 1,
}
logging.info(f"Comparison: {client.compare_gtins(expected_gtins, current_gtins)}")
