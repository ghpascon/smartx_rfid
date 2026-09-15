from smartx_rfid.utils.regex import regex_hex


def get_renner_sku(epc: str) -> str | None:
    if not regex_hex(epc, 24):
        return None
    return str(int(epc[4:16], 16))
