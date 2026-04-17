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
