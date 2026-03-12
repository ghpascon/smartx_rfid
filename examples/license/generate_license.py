import logging
from smartx_rfid.license.main import LicenseManager

logging.basicConfig(level=logging.INFO)


# Instantiate license manager
private_key_path = "license_files/private_key.pem"
private_pem = None
with open(private_key_path, "r") as f:
    private_pem = f.read()
manager = LicenseManager(private_key_pem=private_pem)
logging.info("LicenseManager initialized.")

# License data
data = {"modules": "ALL"}
license = manager.create_license(data, duration_days=7)
logging.info(f"License generated: {license}")
