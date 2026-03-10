import logging

from smartx_rfid.license.main import LicenseManager
from smartx_rfid.db import DatabaseManager
from smartx_rfid.models.license import License

logging.basicConfig(level=logging.INFO)

request_string = input("Enter license request string: ")
license_data = LicenseManager.parse_license_request_string(request_string)
public_key = license_data.get("public_key")
public_key = public_key.strip() if public_key else None
hardware_id = license_data.get("hardware_id")
logging.info(f"Parsed license request - Public Key: {public_key}, Hardware ID: {license_data.get('hardware_id')}")

if not public_key or not hardware_id:
    raise Exception("Public key or hardware ID not found in license request string")

# Initialize database
db = DatabaseManager("mysql+pymysql://smartx:smartx@192.168.1.200:3303/smartx")
db.initialize()


def get_private_key_from_db(public_key: str) -> str:
    with db.get_session() as session:
        license_entry: License = session.query(License).filter_by(public_key=public_key).first()
        if not license_entry:
            raise Exception("Public key not found in database")
        return license_entry.private_key


private_key = get_private_key_from_db(public_key)
logging.info(f"Private key: {private_key}")
license_manager = LicenseManager(private_key_pem=private_key, public_key_pem=public_key)
license_str = license_manager.create_license(
    hardware_id=hardware_id, duration_days=7, data={"example_data": "This is an example license data field"}
)
logging.info(f"Generated license string: {license_str}")
