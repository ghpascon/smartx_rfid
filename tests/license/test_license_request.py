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
