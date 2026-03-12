def generate_zpl_with_params(zpl: str, **kwargs) -> str:
    """
    Replaces ZPL placeholders (e.g., {epc}, {num}) with values provided in kwargs.
    Example:
            generate_zpl_with_params(zpl, epc="123", num="456")
    """
    try:
        return zpl.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing parameter for placeholder: {e}")
