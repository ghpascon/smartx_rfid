import pytest
from smartx_rfid.license.main import LicenseManager


@pytest.fixture
def key_pair():
    priv, pub = LicenseManager.generate_key_pair()
    return priv, pub


@pytest.fixture
def manager(key_pair):
    priv, pub = key_pair
    return LicenseManager(private_key_pem=priv, public_key_pem=pub)


@pytest.fixture
def public_manager(key_pair):
    _, pub = key_pair
    return LicenseManager(public_key_pem=pub)


def test_license_request_string_invalid():
    with pytest.raises(ValueError):
        LicenseManager.parse_license_request_string("not_base64!!")


def test_encode_keys_to_base64_and_from_base64_keys(key_pair):
    priv, pub = key_pair
    b64 = LicenseManager.encode_keys(public_key=pub)
    import base64
    import json

    decoded = json.loads(base64.b64decode(b64).decode())
    assert decoded["public_key"] == pub
    assert "private_key" not in decoded
    manager = LicenseManager.from_encoded_keys(b64)
    assert manager.private_key is None
    assert manager.public_key is not None


def test_encode_keys_to_base64_only_public(key_pair):
    _, pub = key_pair
    b64 = LicenseManager.encode_keys(public_key=pub)
    import base64
    import json

    decoded = json.loads(base64.b64decode(b64).decode())
    assert decoded["public_key"] == pub
    assert "private_key" not in decoded

    manager = LicenseManager.from_encoded_keys(b64)
    assert manager.private_key is None
    assert manager.public_key is not None


def test_from_encoded_keys_invalid():
    with pytest.raises(ValueError):
        LicenseManager.from_encoded_keys("not_base64!!")
