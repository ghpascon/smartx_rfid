"""
Exceções customizadas para o RFID Tag TID Parser.
"""


class TagTidParserError(Exception):
    """Exceção base para erros do TagTidParser."""

    pass


class InvalidTidError(TagTidParserError):
    """Exceção levantada quando o TID fornecido é inválido."""

    pass
