from .SATO._main import SatoPrinter
from .SATO_WS4._main import SatoWs4Printer
from .PRINTRONIX._main import PrintronixPrinter
from .SATO_SBPL._main import SatoSbplPrinter
from .SATO_SBPL.label import SbplLabel
from .SATO_SBPL.protocol import PrinterStatus, RfidResult

# SBPL job (ESC = \x1b): writes an EPC on the tag and prints it as text.
simple_sbpl_example = (
    "\x1bA"
    "\x1bRU,01"
    "\x1bIP0e:h,epc:E20000000000000000000001;"
    "\x1bV50\x1bH50\x1bL0202\x1bXME20000000000000000000001"
    "\x1bQ1"
    "\x1bZ"
)

params_sbpl_example = "\x1bA\x1bRU,01\x1bIP0e:h,epc:{epc};\x1bV50\x1bH50\x1bL0202\x1bXM{epc}\x1bQ1\x1bZ"

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
