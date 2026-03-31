from smartx_rfid.db import DatabaseManager
from smartx_rfid.models.license import License

public_key_path = "license_files/public_key.pem"
private_key_path = "license_files/private_key.pem"
with open(public_key_path, "r") as f:
    public_pem = f.read()
with open(private_key_path, "r") as f:
    private_pem = f.read()


db = DatabaseManager("mysql+pymysql://root:admin@localhost:3306/orders")
db.initialize()
db.register_models(License)
db.create_tables()
with db.get_session() as session:
    license_entry = License(public_key=public_pem, private_key=private_pem)
    session.add(license_entry)
