from pyepc import SGTIN


def get_epc_from_gtin(self, gtin: str, serial: int, company_prefix_length: int = 7):
    try:
        epc = SGTIN.from_sgtin(gtin, serial, company_prefix_length).encode().lower()
    except Exception as e:
        raise ValueError(f"Failed to generate EPC for GTIN {gtin}: {e}")

    # try to decode the EPC back to GTIN
    try:
        decoded_gtin = SGTIN.decode(epc).gtin
    except Exception as e:
        raise ValueError(f"Failed to decode EPC {epc}: {e}")
    if not decoded_gtin == gtin:
        raise ValueError("Failed to match decoded GTIN with original GTIN")
    return epc


def get_gtin_from_epc(epc: str):
    try:
        gtin = SGTIN.decode(epc).gtin
    except Exception:
        gtin = None
    return gtin
