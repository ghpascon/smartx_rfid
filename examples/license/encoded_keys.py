from smartx_rfid.license import LicenseManager

private_key, public_key = LicenseManager.generate_key_pair()

encoded_keys = LicenseManager.encode_keys(public_key=public_key, private_key=private_key)

print("Encoded Keys:", encoded_keys)

# To decode and create a LicenseManager instance
license_manager = LicenseManager.from_encoded_keys(encoded_keys)
license_string = license_manager.create_license({"modules": "test"}, 30)

print("License String:", license_string)

license_manager.load_license(license_string)
print("License Data:", license_manager.license_data)
print("Is License Valid?", license_manager.validate_license())
