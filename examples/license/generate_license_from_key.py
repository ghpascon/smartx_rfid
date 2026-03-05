import logging
from smartx_rfid.license.main import LicenseManager

logging.basicConfig(level=logging.INFO)

private_key_path = "license_files/private_key.pem"
private_pem = None
with open(private_key_path, "r") as f:
    private_pem = f.read()

key = "eyJoYXJkd2FyZV9pZCI6ICIyNGNlOTg2ZGZiM2JhYTVlNGY4ODMxODJhNjY3ZjAyYmI4M2E2OWY2NjFlZjA0MWYzZGI1MDc0ZmVhYjQ3NWU1IiwgInB1YmxpY19rZXkiOiAiLS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS1cbk1JSUJJakFOQmdrcWhraUc5dzBCQVFFRkFBT0NBUThBTUlJQkNnS0NBUUVBc3h6ZlNiUDJqQ2RsT0E4UXZJNnBcbm9QS0NaaFdrNkhxdTFwZnl5TDlIWERUVm9kY2pNYytyWFhOOEltNGtCbjV4ZDB6dnNPaVdRY3ZjK2RFamZEbWNcbk0xNVYwOElrczlxempWVWFWZWp1eWFkdUoxWGxZbTQwaWlHQXZnUjFyblhVNmFwZGVFYWRyQ0V0RFAya2ZvNmNcbkd4L0UrRjk3ZTR4MXNkU1hGZjhDMkF2VWtrM0J2VHRmNGhHME5tWmw2bGIyNHZUTTFJWFpNWVJ2M1psaGczcFpcbnhoclVyL1dlcmk0bUFlRGN3U20ycXV6dnRUZEFDS3lUU00wUW16TmdkREt0WnJWZ1VkN0dCOGRQV29lanB1eTNcbnlibWpFYi93UzNpeitQeUtaRVUvckpxbWNVQnAyNE5ZekRVWFRjVk40RnB1R3doQ1p1USt1U0xKdmEwNlN5dEZcbjF3SURBUUFCXG4tLS0tLUVORCBQVUJMSUMgS0VZLS0tLS1cbiJ9"
manager = LicenseManager(private_key_pem=private_pem)
data = manager.parse_license_request_string(key)
hardware_id = data.get("hardware_id")
logging.info(f"Hardware ID from key: {hardware_id}")
public_key = data.get("public_key")
logging.info(f"Public key from key: {public_key}")

logging.info(
    manager.create_license(
        {"modules": "TESTE"},
        duration_days=7,
        hardware_id=hardware_id,
    )
)
