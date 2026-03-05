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


def test_license_request_string(manager, key_pair):
    _, pub = key_pair
    hardware_id = "TEST-HW-ID"
    req_str = LicenseManager.build_license_request_string(pub, hardware_id=hardware_id)
    decoded = LicenseManager.parse_license_request_string(req_str)
    assert decoded["hardware_id"] == hardware_id
    assert decoded["public_key"] == pub


def test_license_request_string_auto_hw(manager, key_pair):
    _, pub = key_pair
    req_str = LicenseManager.build_license_request_string(pub)
    decoded = LicenseManager.parse_license_request_string(req_str)
    assert "hardware_id" in decoded
    assert decoded["public_key"] == pub


def test_license_request_string_invalid():
    with pytest.raises(ValueError):
        LicenseManager.parse_license_request_string("not_base64!!")
