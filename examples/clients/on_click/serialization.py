from smartx_rfid.clients.on_click import OnClickClient

serialized = OnClickClient.serialize_tag(123456, "e2801190200070a18b9f032a")

print("Serialized:", serialized)

deserialized = OnClickClient.deserialize_tag(serialized)
print("Deserialized:", deserialized)
