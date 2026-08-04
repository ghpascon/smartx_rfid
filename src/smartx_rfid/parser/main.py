import logging
from .rfid_tag_parser.tag_tid_parser import parse_tid
from smartx_rfid.utils import regex_hex
from pyepc import SGTIN


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
