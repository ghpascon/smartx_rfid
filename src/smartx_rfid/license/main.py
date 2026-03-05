import json
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature


class LicenseManager:
    """
    Professional License Manager

    Features:
    - RSA signing
    - Hardware binding
    - Expiration support
    - Dict-like access
    - License request string (for activation systems)
    """

    # ==========================================================
    # INIT
    # ==========================================================
    def __init__(self, private_key_pem: Optional[str] = None, public_key_pem: Optional[str] = None):
        self.private_key = None
        self.public_key = None
        self.license_data: Optional[Dict[str, Any]] = None

        if private_key_pem:
            self.load_private_key(private_key_pem)

        if public_key_pem:
            self.load_public_key(public_key_pem)

    # ==========================================================
    # LICENSE REQUEST STRING
    # ==========================================================
    @staticmethod
    def build_license_request_string(public_key_pem: str, hardware_id: Optional[str] = None) -> str:
        """
        Returns a base64 string containing hardware_id and public_key.
        Useful for license activation systems.
        """

        if hardware_id is None:
            hardware_id = LicenseManager.get_hardware_id()

        payload = json.dumps({"hardware_id": hardware_id, "public_key": public_key_pem}, sort_keys=True).encode()

        return base64.b64encode(payload).decode()

    @staticmethod
    def parse_license_request_string(request_string: str) -> Dict[str, str]:
        """
        Decodes a license request string.
        Returns dict with hardware_id and public_key.
        """

        try:
            payload = base64.b64decode(request_string)
            return json.loads(payload.decode())
        except Exception as e:
            raise ValueError(f"Invalid license request string: {e}")

    # ==========================================================
    # KEY MANAGEMENT
    # ==========================================================
    @staticmethod
    def generate_key_pair(key_size: int = 2048):
        """
        Generate RSA key pair.
        Returns (private_pem, public_pem)
        """

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        public_pem = (
            private_key.public_key()
            .public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )

        return private_pem, public_pem

    def load_private_key(self, private_key_pem: str):
        self.private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)

    def load_public_key(self, public_key_pem: str):
        self.public_key = serialization.load_pem_public_key(public_key_pem.encode())

    # ==========================================================
    # HARDWARE ID
    # ==========================================================
    @staticmethod
    def get_hardware_id() -> str:
        mac = uuid.getnode()
        raw = str(mac).encode()
        return hashlib.sha256(raw).hexdigest()

    # ==========================================================
    # LICENSE CREATION
    # ==========================================================
    def create_license(
        self, data: Dict[str, Any], duration_days: Optional[int] = None, hardware_id: Optional[str] = None
    ) -> str:
        """
        Create and sign license.
        Requires private key.
        """

        if not self.private_key:
            raise Exception("Private key not loaded")

        license_data = data.copy()

        # Hardware binding
        if hardware_id is None:
            hardware_id = self.get_hardware_id()

        license_data["hardware_id"] = hardware_id

        # Expiration
        if duration_days is not None:
            expires = datetime.now() + timedelta(days=duration_days)
            license_data["expires"] = expires.isoformat()
        elif "expires" not in license_data:
            expires = datetime.now() + timedelta(days=365)
            license_data["expires"] = expires.isoformat()

        payload = json.dumps(license_data, sort_keys=True).encode()

        signature = self.private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())

        combined = payload + b"||" + signature
        return base64.b64encode(combined).decode()

    # ==========================================================
    # LICENSE VALIDATION
    # ==========================================================
    def load_license(self, license_string: str):
        if not self.public_key:
            raise Exception("Public key not loaded")

        decoded = base64.b64decode(license_string)
        payload, signature = decoded.split(b"||")

        # Verify signature
        try:
            self.public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            raise Exception("Invalid license signature")

        data = json.loads(payload.decode())

        # Hardware validation
        if data.get("hardware_id") != self.get_hardware_id():
            raise Exception("License not valid for this hardware")

        # Expiration validation
        if data.get("expires"):
            exp = datetime.fromisoformat(data["expires"])
            if datetime.now() > exp:
                raise Exception("License expired")

        self.license_data = data
        logging.info("License loaded and valid")

    def validate_license(self, license_string: str) -> bool:
        try:
            self.load_license(license_string)
            return True
        except Exception as e:
            logging.info(f"License validation failed: {e}")
            return False

    # ==========================================================
    # DICT-LIKE ACCESS
    # ==========================================================
    def get(self, key, default=None):
        if not self.license_data:
            return default
        return self.license_data.get(key, default)

    def __getitem__(self, key):
        if not self.license_data:
            raise Exception("License not loaded")
        return self.license_data[key]

    def __contains__(self, key):
        if not self.license_data:
            return False
        return key in self.license_data

    # ==========================================================
    # UTIL
    # ==========================================================
    def is_loaded(self) -> bool:
        return self.license_data is not None
