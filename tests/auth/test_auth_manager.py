from __future__ import annotations


import pytest

from smartx_rfid.auth.main import AuthManager


SECRET = "test-secret-key-with-enough-length-32b!"
STRONG_PASSWORD = "Secure@123"


# =====================================================
# FIXTURES
# =====================================================


@pytest.fixture
def auth() -> AuthManager:
    return AuthManager(secret=SECRET, expiration_minutes=15)


@pytest.fixture
def expired_auth() -> AuthManager:
    return AuthManager(secret=SECRET, expiration_minutes=-1)


# =====================================================
# __init__
# =====================================================


def test_default_secret_is_set():
    """When no secret is provided a non-empty secret is generated."""
    a = AuthManager()
    assert a._secret


def test_custom_secret_is_stored(auth: AuthManager):
    assert auth._secret == SECRET


def test_default_expiration_is_15():
    a = AuthManager(secret=SECRET)
    assert a._expiration_minutes == 15


def test_custom_expiration_is_stored():
    a = AuthManager(secret=SECRET, expiration_minutes=30)
    assert a._expiration_minutes == 30


def test_default_algorithm_is_hs256(auth: AuthManager):
    assert auth._algorithm == "HS256"


# =====================================================
# hash_password
# =====================================================


def test_hash_password_returns_string(auth: AuthManager):
    hashed = auth.hash_password(STRONG_PASSWORD)
    assert isinstance(hashed, str)
    assert hashed != STRONG_PASSWORD


def test_hash_password_different_hashes_for_same_input(auth: AuthManager):
    h1 = auth.hash_password(STRONG_PASSWORD)
    h2 = auth.hash_password(STRONG_PASSWORD)
    assert h1 != h2  # Argon2 uses random salt


def test_hash_password_raises_on_empty(auth: AuthManager):
    with pytest.raises(ValueError, match="Password cannot be empty"):
        auth.hash_password("")


# =====================================================
# _validate_password_strength
# =====================================================


@pytest.mark.parametrize(
    "password,missing",
    [
        ("short1A!", None),  # valid — exactly 8 chars
        ("nouppercase1!", "uppercase"),  # no uppercase
        ("NOLOWERCASE1!", "lowercase"),  # no lowercase
        ("NoDigitHere!", "digit"),  # no digit
        ("NoSpecial123", "special"),  # no special char
        ("Ab1!", "8 characters"),  # too short
    ],
)
def test_password_validation(auth: AuthManager, password: str, missing: str | None):
    if missing is None:
        # Should not raise
        auth._validate_password_strength(password)
    else:
        with pytest.raises(ValueError, match=missing):
            auth._validate_password_strength(password)


# =====================================================
# verify_password
# =====================================================


def test_verify_password_correct(auth: AuthManager):
    hashed = auth.hash_password(STRONG_PASSWORD)
    assert auth.verify_password(STRONG_PASSWORD, hashed) is True


def test_verify_password_wrong(auth: AuthManager):
    hashed = auth.hash_password(STRONG_PASSWORD)
    assert auth.verify_password("Wrong@999", hashed) is False


def test_verify_password_invalid_hash(auth: AuthManager):
    assert auth.verify_password("anything", "not-a-valid-hash") is False


# =====================================================
# create_token
# =====================================================


def test_create_token_returns_string(auth: AuthManager):
    token = auth.create_token({"user_id": 1})
    assert isinstance(token, str)


def test_create_token_contains_claims(auth: AuthManager):
    token = auth.create_token({"user_id": 42, "role": "admin"})
    valid, payload = auth.decode_token(token)
    assert valid is True
    assert payload is not None
    assert payload["user_id"] == 42
    assert payload["role"] == "admin"
    assert "iat" in payload
    assert "exp" in payload


def test_create_token_raises_on_non_dict(auth: AuthManager):
    with pytest.raises(TypeError, match="payload must be a dictionary"):
        auth.create_token("not-a-dict")  # type: ignore[arg-type]


def test_create_token_raises_on_list(auth: AuthManager):
    with pytest.raises(TypeError):
        auth.create_token([1, 2, 3])  # type: ignore[arg-type]


# =====================================================
# decode_token
# =====================================================


def test_decode_token_valid(auth: AuthManager):
    token = auth.create_token({"user_id": 7})
    ok, payload = auth.decode_token(token)
    assert ok is True
    assert payload is not None
    assert payload["user_id"] == 7


def test_decode_token_contains_standard_claims(auth: AuthManager):
    token = auth.create_token({"sub": "user@example.com"})
    ok, payload = auth.decode_token(token)
    assert ok is True
    assert "iat" in payload
    assert "exp" in payload
    assert payload["sub"] == "user@example.com"


def test_decode_token_expired(expired_auth: AuthManager):
    token = expired_auth.create_token({"user_id": 1})
    ok, payload = expired_auth.decode_token(token)
    assert ok is False
    assert payload is None


def test_decode_token_wrong_secret(auth: AuthManager):
    token = auth.create_token({"user_id": 1})
    other = AuthManager(secret="totally-different-secret-key-32b!!")
    ok, payload = other.decode_token(token)
    assert ok is False
    assert payload is None


def test_decode_token_tampered(auth: AuthManager):
    token = auth.create_token({"user_id": 1})
    tampered = token[:-4] + "XXXX"
    ok, payload = auth.decode_token(tampered)
    assert ok is False
    assert payload is None


def test_decode_token_garbage_string(auth: AuthManager):
    ok, payload = auth.decode_token("not.a.token")
    assert ok is False
    assert payload is None
