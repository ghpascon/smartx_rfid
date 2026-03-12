"""
RFID Tag TID Parser

Um parser Python para análise de TID (Tag Identifier) de tags RFID.
Extrai informações como fabricante, modelo, número serial e outras características.
"""

from .tag_tid_parser import TagTidParser, parse_tid, get_serial_from_tid
from .exceptions import TagTidParserError, InvalidTidError

__version__ = "1.0.0"
__author__ = "Seu Nome"
__email__ = "seu.email@exemplo.com"

__all__ = ["TagTidParser", "parse_tid", "get_serial_from_tid", "TagTidParserError", "InvalidTidError"]
