from smartx_rfid.utils import regex_hex
import logging


def rchlo_get_sku_from_epc(epc: str):
    if not regex_hex(epc, 24):
        logging.warning(f"Invalid EPC format: {epc}")
        return None
    return epc[3:14]
