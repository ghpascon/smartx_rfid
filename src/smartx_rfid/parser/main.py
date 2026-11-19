import logging
from .rfid_tag_parser.tag_tid_parser import parse_tid
from pyepc import SGTIN
import re


def regex_hex(value: str, length: int | None = None) -> bool:
    """
    Validate if the given value is a valid hexadecimal string.
    If length is specified, the string must have exactly that many characters.
    """
    if length is None:
        pattern = r"^[0-9A-Fa-f]+$"
    else:
        pattern = rf"^[0-9A-Fa-f]{{{length}}}$"
    return bool(re.match(pattern, value))


def get_serial_from_tid(tid: str) -> str | None:
    """
    Extract serial number from TID.
    """
    # validate TID format
    if not regex_hex(tid, 24):
        return None

    try:
        # SUFIX
        parse = parse_tid(tid)
        if not parse:
            return None

        serial = parse.get("serial_decimal")
        if serial is None:
            return None

        return str(serial)
    except Exception as e:
        logging.error(f"Parse ERROR: {e}")
        return None


def serialize_gtin(gtin: str, serial: str) -> str:
    """
    Serialize GTIN and serial number into a single string.
    """
    sgtin = SGTIN.from_sgtin(gtin.zfill(14), serial, 7)
    sgtin = sgtin.encode().lower()
    return sgtin


def serialize_split(product_code: str, serial: str, product_code_length: int = 12) -> str:
    """
    Serialize product code and serial number into a single string.
    """
    serial = str(serial)
    if len(product_code) > product_code_length:
        raise ValueError(f"Product code length exceeds the specified limit of {product_code_length}")
    if len(serial) + len(product_code) > 24:
        raise ValueError("Combined length of product code and serial number exceeds 24 characters")

    epc = f"{product_code.zfill(product_code_length)}{serial.zfill(24 - product_code_length)}"
    if not regex_hex(epc, 24):
        raise ValueError("Serialized string must be exactly 24 hexadecimal characters long")
    return epc


def deserialize_split(serialized: str, product_code_length: int = 12) -> tuple[str, str]:
    """
    Deserialize a serialized string into product code and serial number.
    """
    if not regex_hex(serialized, 24):
        raise ValueError("Serialized string must be exactly 24 hexadecimal characters long")
    product_code = serialized[:product_code_length].lstrip("0")
    serial = serialized[product_code_length:].lstrip("0")
    return product_code, serial
