from smartx_rfid.clients.renner import renner_serialize_epc_by_address, renner_get_address_by_epc

address = "EN0.C131.S002.N1.0"
epc = renner_serialize_epc_by_address(address)
print(f"Original Address: {address}")
print(f"Serialized EPC: {epc}")
decoded_address = renner_get_address_by_epc(epc)
print(f"Decoded Address: {decoded_address}")
