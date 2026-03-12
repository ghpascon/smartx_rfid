EPC_LENGTH = 24


def data_to_hex(data: str, pad_char: str = " ") -> str:
    return "".join([f"{ord(c):02X}" for c in data.rjust(12, pad_char)])


def parse_encode_rule(params: str) -> dict:
    """Parse encode rule string (key=value\\r\\n pairs) into a dict."""
    rule = {}
    for line in params.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            rule[key.strip()] = value.strip()
    return rule


def build_epc(serial: int, rule: dict) -> str:
    """Build a single EPC string from a serial number and encode rule.

    The result is always exactly 24 hex characters (96-bit EPC).
    """
    # prefix = rule.get("EPCPrefix", "") or ""
    # suffix = rule.get("EPCSuffix", "") or ""
    # pad_char = rule.get("PadChar", "0") or "0"
    # pad_align = rule.get("PadAlign", "LEFT").upper()
    # barcode_prefix_len = int(rule.get("BarcodePrefixLength", 0) or 0)
    # barcode_suffix_len = int(rule.get("BarcodeSuffixLength", 0) or 0)
    # convert_to_hex = (rule.get("ConvertToHex", "ALL") or "ALL").upper()

    return None
