from .SATO._main import SatoPrinter
from .SATO_WS4._main import SatoWs4Printer

simple_zpl_example = """
^XA
^RS8
^RFW,H,2,12
^FD000000000000000000000001^FS

^FO50,50
^A0N,40,40
^FD000000000000000000000001^FS
^XZ
"""

params_zpl_example = """
^XA
^RS8
^RFW,H,2,12
^FD{sequential}^FS

^FO50,50
^A0N,40,40
^FD{epc}^FS
^XZ
"""
