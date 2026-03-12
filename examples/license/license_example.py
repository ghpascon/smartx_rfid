import logging
from smartx_rfid.license.main import LicenseManager
import os

logging.basicConfig(level=logging.INFO)


# Generate key pair
private_pem, public_pem = LicenseManager.generate_key_pair()
logging.info("Key pair generated.")

# Save public key to file
license_dir = "license_files"
os.makedirs(license_dir, exist_ok=True)
public_key_path = os.path.join(license_dir, "public_key.pem")
private_key_path = os.path.join(license_dir, "private_key.pem")
with open(public_key_path, "w") as f:
    f.write(public_pem)
with open(private_key_path, "w") as f:
    f.write(private_pem)
logging.info(f"Public key saved to {public_key_path}")
logging.info(f"Private key saved to {private_key_path}")

# Instantiate license manager
manager = LicenseManager(private_key_pem=private_pem, public_key_pem=public_pem)
logging.info("LicenseManager initialized.")

# License data
data = {"modules": ["rfid", "printer"], "readers": ["R700", "X714"], "custom": {"foo": "bar"}}

# Create license valid for 7 days
license_str = manager.create_license(data, duration_days=7)
logging.info(f"License generated: {license_str}")

# Save license to file
license_path = os.path.join(license_dir, "license.txt")
with open(license_path, "w") as f:
    f.write(license_str)
logging.info(f"License saved to {license_path}")

# Validate license
manager2 = LicenseManager(public_key_pem=public_pem)
manager2.load_license(license_str)
logging.info(f"License is valid! Data: {manager2.license_data}")

# Dict-like access
logging.info(f"Enabled modules: {manager2.get('modules')}")
logging.info(f"Expires at: {manager2['expires']}")
