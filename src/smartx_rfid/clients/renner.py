from smartx_rfid.utils.regex import regex_hex


def get_renner_sku(epc: str) -> str | None:
    if not regex_hex(epc, 24):
        return None
    return str(int(epc[4:16], 16))


def renner_get_epc_from_sku(sku: str, serial=1) -> str:
    sku_value = int(sku)
    serial_value = int(serial)
    if not 0 <= sku_value < 16**12:
        raise ValueError("SKU must fit in 12 hexadecimal characters")
    if not 0 <= serial_value < 16**8:
        raise ValueError("Serial must fit in 8 hexadecimal characters")
    return f"0000{sku_value:012x}{serial_value:08x}"


def renner_serialize_epc_by_address(address: str) -> str:
    # EN0.C131.S002.N1.0
    parts = address.split(".")
    if len(parts) != 5:
        raise ValueError("Invalid address format")
    prefix = "edc0"
    epc = (
        prefix
        + parts[0][2:].zfill(4)
        + parts[1][1:].zfill(4)
        + parts[2][1:].zfill(4)
        + parts[3][1:].zfill(4)
        + parts[4].zfill(4)
    )
    return epc


def renner_get_address_by_epc(epc: str) -> str | None:
    if not regex_hex(epc, 24):
        raise ValueError("Invalid EPC format")

    parts = list(epc[index : index + 4] for index in range(4, 24, 4))
    parts[0] = "EN" + (parts[0].lstrip("0") or "0")
    parts[1] = "C" + (parts[1].lstrip("0").zfill(3))
    parts[2] = "S" + (parts[2].lstrip("0").zfill(3))
    parts[3] = "N" + (parts[3].lstrip("0") or "0")
    parts[4] = parts[4].lstrip("0") or "0"
    return ".".join(parts)
