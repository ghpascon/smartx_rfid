import base64
from smartx_rfid.models.license import License


def test_public_key_base64_set_and_get():
    original = "chave_publica_teste_123"
    lic = License()
    lic.public_key = original
    # O valor armazenado deve ser base64
    assert lic.public_key != original
    # O valor decodificado deve ser igual ao original
    assert lic.public_key_decoded == original

    # Testa se ao setar já em base64, não quebra
    b64 = base64.b64encode(original.encode("utf-8")).decode("utf-8")
    lic2 = License()
    lic2.public_key = b64
    assert lic2.public_key == b64
    assert lic2.public_key_decoded == original


def test_public_key_strip():
    lic = License()
    lic.public_key = "  chave_com_espaco  "
    assert lic.public_key_decoded == "chave_com_espaco"
