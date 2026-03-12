import pytest
from smartx_rfid.license.main import LicenseManager
from datetime import datetime, timedelta


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


def test_license_creation_and_validation(manager, public_manager):
    data = {"modules": ["rfid", "printer"], "readers": ["R700", "X714"], "custom": {"foo": "bar"}}
    license_str = manager.create_license(data, duration_days=2)
    assert isinstance(license_str, str)

    public_manager.load_license(license_str)
    assert public_manager.is_loaded()
    assert "modules" in public_manager.license_data
    assert "expires" in public_manager.license_data
    # Expiration should be in the future
    exp = datetime.fromisoformat(public_manager.license_data["expires"])
    assert exp > datetime.now()


def test_expired_license(manager, public_manager):
    data = {"modules": ["rfid"]}
    expired_date = (datetime.now() - timedelta(days=1)).isoformat()
    data["expires"] = expired_date
    license_str = manager.create_license(data)
    with pytest.raises(Exception, match="License expired"):
        public_manager.load_license(license_str)


def test_hardware_binding(manager, public_manager):
    data = {"modules": ["rfid"]}
    license_str = manager.create_license(data, duration_days=1)
    public_manager.load_license(license_str)
    # Should match hardware id
    assert public_manager.license_data["hardware_id"] == LicenseManager.get_hardware_id()
