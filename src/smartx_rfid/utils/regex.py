import re


def regex_hex(value: str, length: int = 24) -> bool:
    """
    Validate if the given value is a valid EPC (24 hexadecimal characters).
    """
    pattern = rf"^[0-9A-Fa-f]{{{length}}}$"
    return bool(re.match(pattern, value))
