"""SBPL label builder.

:class:`SbplLabel` builds a complete SBPL job (``ESC A ... ESC Z``) with a fluent API::

    label = (
        SbplLabel()
        .text("HELLO", "XM", x=50, y=50)
        .code128("123456", x=50, y=150, height=100)
        .qr_code("https://smartx.com.br", x=400, y=50, cell=5)
        .write_rfid(epc="E2000000000000000000AAAA")
        .quantity(2)
    )
    printer.print(label)

Every command follows the CL4NX Plus / CL6NX Plus Programming Reference.
Text is encoded with the printer code page (``cp858`` by default).
"""

from __future__ import annotations

from pathlib import Path

from .protocol import ESC

BITMAP_FONTS = frozenset({"XU", "XS", "XM", "XB", "XL", "OA", "OB", "U", "S", "M", "WB", "WL"})
SMOOTHING_FONTS = frozenset({"XB", "XL", "WB", "WL"})
OUTLINE_FONTS = frozenset({"X20", "X21", "X22", "X23", "X24"})

BARCODE_TYPES = {
    "codabar": "0",
    "code39": "1",
    "itf": "2",
    "ean13": "3",
    "ean8": "4",
    "industrial2of5": "5",
    "matrix2of5": "6",
    "msi": "A",
    "upce": "E",
    "upca": "H",
}
_HRI_BARCODES = {"ean13": "3", "ean8": "4", "upca": "H"}
_RATIO_COMMANDS = {"1:3": "B", "1:2": "D", "2:5": "BD"}

CODE_PAGES = frozenset(
    {
        "858",
        "88591",
        "88592",
        "88599",
        "850",
        "852",
        "855",
        "857",
        "737",
        "866",
        "1250",
        "1251",
        "1252",
        "1253",
        "1254",
        "1257",
        "869",
        "201",
        "UTF-8",
    }
)

#: Maps the ``<CE>`` code page to the Python codec used to encode text.
_CODECS = {
    "858": "cp858",
    "88591": "iso8859-1",
    "88592": "iso8859-2",
    "88599": "iso8859-9",
    "850": "cp850",
    "852": "cp852",
    "855": "cp855",
    "857": "cp857",
    "737": "cp737",
    "866": "cp866",
    "1250": "cp1250",
    "1251": "cp1251",
    "1252": "cp1252",
    "1253": "cp1253",
    "1254": "cp1254",
    "1257": "cp1257",
    "869": "cp869",
    "201": "latin-1",
    "UTF-8": "utf-8",
}


def _check(name: str, value: int, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high} (got {value!r})")
    return value


class SbplLabel:
    """Fluent builder for one SBPL job."""

    def __init__(self, encoding: str = "cp858") -> None:
        self.encoding = encoding
        self._parts: list[bytes] = []
        self._rfid: list[bytes] = []
        self._quantity = 1

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _encode(self, text: str | bytes, encoding: str | None = None) -> bytes:
        if isinstance(text, bytes):
            return text
        return text.encode(encoding or self.encoding, errors="replace")

    def _cmd(self, name: str, params: str | bytes = "", *, encoding: str | None = None) -> SbplLabel:
        self._parts.append(ESC + name.encode("ascii") + self._encode(params, encoding))
        return self

    def _rfid_cmd(self, name: str, params: str) -> SbplLabel:
        """RFID commands are emitted right after ``<A>``, before the printed items."""
        self._rfid.append(ESC + name.encode("ascii") + params.encode("ascii"))
        return self

    def _prefix(
        self,
        x: int | None = None,
        y: int | None = None,
        rotation: int | None = None,
        scale: int | tuple[int, int] | None = None,
        pitch: int | None = None,
    ) -> None:
        if rotation is not None:
            self.rotate(rotation)
        if y is not None:
            _check("y", y, 0, 99999)
            self._cmd("V", str(y))
        if x is not None:
            _check("x", x, 0, 9999)
            self._cmd("H", str(x))
        if pitch is not None:
            self.pitch(pitch)
        if scale is not None:
            self.enlarge(*((scale, scale) if isinstance(scale, int) else scale))

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #
    def raw(self, data: str | bytes) -> SbplLabel:
        """Append raw SBPL data (use ``\\x1b`` for ESC)."""
        self._parts.append(self._encode(data))
        return self

    def build(self, *, frame: bool = False) -> bytes:
        """Return the job bytes. ``frame=True`` wraps them with STX/ETX."""
        body = (
            ESC
            + b"A"
            + b"".join(self._rfid)
            + b"".join(self._parts)
            + ESC
            + b"Q"
            + str(self._quantity).encode()
            + ESC
            + b"Z"
        )
        return b"\x02" + body + b"\x03" if frame else body

    def __bytes__(self) -> bytes:
        return self.build()

    def __repr__(self) -> str:
        return f"SbplLabel({self.build().replace(ESC, b'<ESC>')!r})"

    # ------------------------------------------------------------------ #
    # Job control
    # ------------------------------------------------------------------ #
    def quantity(self, quantity: int) -> SbplLabel:
        """Number of labels to print (always emitted last, as required by SBPL)."""
        self._quantity = _check("quantity", quantity, 1, 999999)
        return self

    def job_id(self, job_id: int) -> SbplLabel:
        """``<ID>`` job id returned by the ENQ status protocols (0-99999)."""
        _check("job_id", job_id, 0, 99999)
        return self._cmd("ID", f"{job_id:02d}" if job_id <= 99 else f"{job_id:05d}")

    def job_name(self, name: str) -> SbplLabel:
        """``<WK>`` job name returned by the Status4 protocol (16 characters max)."""
        if len(name) > 16:
            raise ValueError("job name must have at most 16 characters")
        return self._cmd("WK", name)

    # ------------------------------------------------------------------ #
    # Media / print settings
    # ------------------------------------------------------------------ #
    def media_size(self, height: int, width: int) -> SbplLabel:
        """``<A1>`` label size in dots."""
        _check("height", height, 1, 99999)
        _check("width", width, 1, 9999)
        return self._cmd("A1", f"V{height:05d}H{width:04d}")

    def base_reference(self, vertical: int = 0, horizontal: int = 0) -> SbplLabel:
        """``<A3>`` base reference point correction in dots (signed)."""
        _check("vertical", vertical, -99999, 99999)
        _check("horizontal", horizontal, -9999, 9999)
        return self._cmd("A3", f"V{vertical:+06d}H{horizontal:+05d}")

    def speed(self, speed: int) -> SbplLabel:
        """``<CS>`` print speed (range depends on the model)."""
        return self._cmd("CS", str(_check("speed", speed, 1, 99)))

    def darkness(self, level: int, mode: str = "A") -> SbplLabel:
        """``<#F>`` print darkness: level 1 (lightest) to 10 (darkest), mode A-F."""
        _check("level", level, 1, 10)
        if mode not in tuple("ABCDEF"):
            raise ValueError("darkness mode must be a letter from A to F")
        return self._cmd("#F", f"{level}{mode}")

    def print_mode(self, mode: str | int) -> SbplLabel:
        """``<PM>`` 0 continuous, 1 tear-off, 2/3/4 cutter, 5 linerless, 7/8 dispense, B cutter motion."""
        mode = str(mode).upper()
        if mode not in tuple("01234578B"):
            raise ValueError(f"invalid print mode {mode!r}")
        return self._cmd("PM", mode)

    def print_method(self, direct_thermal: bool = False) -> SbplLabel:
        """``<PH>`` 0 thermal transfer, 1 direct thermal."""
        return self._cmd("PH", "1" if direct_thermal else "0")

    def sensor(self, sensor_type: str | int) -> SbplLabel:
        """``<IG>`` sensor: ``reflective`` (0), ``gap`` (1) or ``none`` (2)."""
        types = {"reflective": "0", "gap": "1", "none": "2", 0: "0", 1: "1", 2: "2"}
        if sensor_type not in types:
            raise ValueError("sensor must be 'reflective', 'gap' or 'none'")
        return self._cmd("IG", types[sensor_type])

    def offset(self, target: int, dots: int) -> SbplLabel:
        """``<PO>`` media stop offset. target: 0 cut, 1 dispenser, 2 tear-off, 3 print start; dots -99..99."""
        _check("target", target, 0, 3)
        _check("dots", dots, -99, 99)
        return self._cmd("PO", f"{target}{'+' if dots >= 0 else '-'}{abs(dots):02d}")

    def code_page(self, code_page: str | int, persist: bool = False) -> SbplLabel:
        """``<CE>`` European code page. The text encoder switches to the matching codec."""
        name = str(code_page)
        if name not in CODE_PAGES:
            raise ValueError(f"unsupported code page {name!r}")
        self._cmd("CE", name + (",P" if persist else ""))
        self.encoding = _CODECS[name]
        return self

    def cut_every(self, labels: int) -> SbplLabel:
        """``<CT>`` cut every ``labels`` labels (0 = never). Cutter models only."""
        return self._cmd("CT", str(_check("labels", labels, 0, 9999)))

    def multiple_cut(self, labels: int) -> SbplLabel:
        """``<~>`` number of labels printed between cuts (0 = never). Cutter models only."""
        return self._cmd("~", str(_check("labels", labels, 0, 9999)))

    def auto_line_feed(self, dots: int) -> SbplLabel:
        """``<E>`` line spacing used when the text contains CR."""
        return self._cmd("E", str(_check("dots", dots, 0, 999)))

    def tear_off(self) -> SbplLabel:
        """``<TK>`` forced tear-off (must be sent alone)."""
        return self._cmd("TK")

    # ------------------------------------------------------------------ #
    # Modifiers
    # ------------------------------------------------------------------ #
    def position(self, x: int, y: int) -> SbplLabel:
        """Absolute position in dots: ``<V>y<H>x``."""
        self._prefix(x=x, y=y)
        return self

    def rotate(self, rotation: int) -> SbplLabel:
        """``<%>`` counter-clockwise rotation: 0, 1 (90), 2 (180), 3 (270)."""
        return self._cmd("%", str(_check("rotation", rotation, 0, 3)))

    def enlarge(self, horizontal: int = 1, vertical: int = 1) -> SbplLabel:
        """``<L>`` enlargement ratio (1-36)."""
        _check("horizontal", horizontal, 1, 36)
        _check("vertical", vertical, 1, 36)
        return self._cmd("L", f"{horizontal:02d}{vertical:02d}")

    def pitch(self, dots: int) -> SbplLabel:
        """``<P>`` character pitch in dots."""
        return self._cmd("P", f"{_check('pitch', dots, 0, 99):02d}")

    def proportional_pitch(self, enabled: bool = True) -> SbplLabel:
        """``<PS>`` / ``<PR>`` proportional pitch."""
        return self._cmd("PS" if enabled else "PR")

    def mirror(self, horizontal: int | None = None, vertical: int | None = None) -> SbplLabel:
        """``<RM>`` mirror image of an area (dots). Without arguments mirrors the whole label."""
        if horizontal is None and vertical is None:
            return self._cmd("RM")
        return self._cmd(
            "RM", f"{_check('horizontal', horizontal or 0, 0, 9999)},{_check('vertical', vertical or 0, 0, 99999)}"
        )

    def reverse(self, horizontal: int, vertical: int) -> SbplLabel:
        """``<(>`` reverse (white on black) area starting at the current position."""
        return self._cmd("(", f"{_check('horizontal', horizontal, 1, 9999)},{_check('vertical', vertical, 1, 99999)}")

    # ------------------------------------------------------------------ #
    # Text
    # ------------------------------------------------------------------ #
    def text(
        self,
        data: str | bytes,
        font: str = "XM",
        x: int | None = None,
        y: int | None = None,
        *,
        scale: int | tuple[int, int] | None = None,
        pitch: int | None = None,
        rotation: int | None = None,
        smoothing: bool = False,
    ) -> SbplLabel:
        """Print text with a built-in bitmap (XU XS XM XB XL OA OB U S M WB WL) or outline (X20-X24) font."""
        font = font.upper()
        self._prefix(x, y, rotation, scale, pitch)
        if font in OUTLINE_FONTS:
            return self._cmd(font, b"," + self._encode(data))
        if font not in BITMAP_FONTS:
            raise ValueError(f"unknown font {font!r}")
        if font in SMOOTHING_FONTS:
            return self._cmd(font, b"1" + self._encode(data) if smoothing else b"0" + self._encode(data))
        return self._cmd(font, data)

    def cg_text(
        self,
        data: str,
        width: int | str = 24,
        height: int | str = 24,
        x: int | None = None,
        y: int | None = None,
        *,
        font: str = "A",
        bold: bool = False,
        italic: bool = False,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<RD>`` CG font (``A`` = SATO CG Sleek, ``B`` = SATO CG Stream). Size in dots or ``"P12"`` points."""
        if font not in ("A", "B"):
            raise ValueError("font must be 'A' (CG Sleek) or 'B' (CG Stream)")
        style = "0" if not (bold or italic) else "1" if bold and not italic else "2" if italic and not bold else "3"
        self._prefix(x, y, rotation)
        return self._cmd("RD", f"{font}0{style},{self._size(width)},{self._size(height)},{data}")

    def scalable_text(
        self,
        data: str,
        width: int | str = 40,
        height: int | str = 40,
        x: int | None = None,
        y: int | None = None,
        *,
        font_set: str = "SATOCGStream.ttf",
        bold: bool = False,
        italic: bool = False,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<RH>`` scalable (TrueType) font. Text is sent as UTF-8, so any Unicode character is available."""
        style = 0 + (1 if bold else 0) + (2 if italic else 0)
        self._prefix(x, y, rotation)
        payload = f"0,{font_set},{style},{self._size(width)},{self._size(height)},".encode("ascii") + data.encode(
            "utf-8"
        )
        return self._cmd("RH", payload)

    @staticmethod
    def _size(value: int | str) -> str:
        if isinstance(value, str):
            if not (value.upper().startswith("P") and value[1:].isdigit()):
                raise ValueError("size must be dots or points such as 'P12'")
            return f"P{int(value[1:]):02d}"
        return f"{_check('size', value, 20, 999):03d}"

    # ------------------------------------------------------------------ #
    # Barcodes
    # ------------------------------------------------------------------ #
    def barcode(
        self,
        kind: str,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        narrow: int = 2,
        height: int = 100,
        ratio: str | None = None,
        hri_font: str | None = None,
        rotation: int | None = None,
    ) -> SbplLabel:
        """1D barcode (codabar, code39, itf, ean13, ean8, industrial2of5, matrix2of5, msi, upce, upca).

        ``ratio`` selects ``<B>`` (``"1:3"``), ``<D>`` (``"1:2"``) or ``<BD>`` (``"2:5"``).
        ``hri_font`` prints the human readable text (ean13, ean8 and upca only).
        """
        kind = kind.lower()
        if kind not in BARCODE_TYPES:
            raise ValueError(f"unknown barcode type {kind!r}")
        _check("narrow", narrow, 1, 36)
        _check("height", height, 1, 999)
        if kind == "itf" and len(data) % 2:
            data = "0" + data
        if kind == "code39" and not (data.startswith("*") and data.endswith("*")):
            data = f"*{data}*"
        self._prefix(x, y, rotation)
        code = BARCODE_TYPES[kind]
        if hri_font:
            if kind not in _HRI_BARCODES:
                raise ValueError("hri_font is only available for ean13, ean8 and upca")
            self._cmd("D", f"{code}{narrow:02d}{height:03d}{data}")
            return self.text(data, hri_font)
        command = _RATIO_COMMANDS.get(ratio or "1:3")
        if command is None:
            raise ValueError("ratio must be '1:3', '1:2' or '2:5'")
        return self._cmd(command, f"{code}{narrow:02d}{height:03d}{data}")

    def code128(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        narrow: int = 2,
        height: int = 100,
        subset: str = "auto",
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<BG>`` CODE128. ``subset``: ``auto``, ``A``, ``B`` or ``C`` (digits only, even length)."""
        subset = subset.upper()
        if subset == "AUTO":
            subset = "C" if data.isdigit() and len(data) % 2 == 0 else "B"
        starts = {"A": ">G", "B": ">H", "C": ">I"}
        if subset not in starts:
            raise ValueError("subset must be 'auto', 'A', 'B' or 'C'")
        _check("narrow", narrow, 1, 36)
        _check("height", height, 1, 999)
        self._prefix(x, y, rotation)
        return self._cmd("BG", f"{narrow:02d}{height:03d}{starts[subset]}{data}")

    def code93(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        narrow: int = 2,
        height: int = 100,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<BC>`` CODE93."""
        _check("narrow", narrow, 1, 36)
        _check("height", height, 1, 999)
        _check("data length", len(data), 1, 99)
        self._prefix(x, y, rotation)
        return self._cmd("BC", f"{narrow:02d}{height:03d}{len(data):02d}{data}")

    def gs1_128(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        narrow: int = 2,
        height: int = 100,
        hri: str = "below",
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<BI>`` GS1-128 standard carton id: 17 digits (the check digit is added by the printer)."""
        if not (data.isdigit() and len(data) == 17):
            raise ValueError("GS1-128 data must have exactly 17 digits")
        hri_codes = {"none": "0", "above": "1", "below": "2"}
        if hri not in hri_codes:
            raise ValueError("hri must be 'none', 'above' or 'below'")
        _check("narrow", narrow, 1, 36)
        _check("height", height, 1, 999)
        self._prefix(x, y, rotation)
        return self._cmd("BI", f"{narrow:02d}{height:03d}{hri_codes[hri]}{data}")

    # ------------------------------------------------------------------ #
    # 2D codes
    # ------------------------------------------------------------------ #
    def qr_code(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        cell: int = 4,
        error_correction: str = "M",
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<2D30>`` QR Code (model 2) with automatic data mode."""
        if error_correction not in ("L", "M", "Q", "H"):
            raise ValueError("error_correction must be L, M, Q or H")
        _check("cell", cell, 1, 99)
        payload = data.encode("utf-8")
        _check("data length", len(payload), 1, 2953)
        self._prefix(x, y, rotation)
        self._cmd("2D30", f",{error_correction},{cell:02d},1,0")
        return self._cmd("DN", f"{len(payload):04d},".encode("ascii") + payload)

    def data_matrix(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        cell: int = 4,
        columns: int = 0,
        rows: int = 0,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<2D50>`` DataMatrix ECC200. ``columns``/``rows`` = 0 selects the size automatically."""
        _check("cell", cell, 1, 99)
        if columns:
            _check("columns", columns, 10, 144)
        if rows:
            _check("rows", rows, 8, 144)
        payload = data.encode("utf-8").replace(b"~", b"~~")
        _check("data length", len(payload), 1, 3116)
        self._prefix(x, y, rotation)
        self._cmd("2D50", f",{cell:02d},{cell:02d},{columns:03d},{rows:03d}")
        return self._cmd("DN", f"{len(payload):04d},".encode("ascii") + payload)

    def pdf417(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        module_width: int = 2,
        module_height: int = 6,
        security: int = 3,
        columns: int = 0,
        rows: int = 0,
        truncated: bool = False,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<2D10>`` PDF417. ``columns``/``rows`` = 0 selects the size automatically."""
        _check("module_width", module_width, 1, 27)
        _check("module_height", module_height, 1, 72)
        _check("security", security, 0, 8)
        if columns:
            _check("columns", columns, 1, 30)
        if rows:
            _check("rows", rows, 3, 90)
        payload = data.encode("utf-8")
        _check("data length", len(payload), 1, 2681)
        self._prefix(x, y, rotation)
        self._cmd(
            "2D10",
            f",{module_width:02d},{module_height:02d},{security},{columns:02d},{rows:02d}"
            + (",1" if truncated else ""),
        )
        return self._cmd("DN", f"{len(payload):04d},".encode("ascii") + payload)

    def aztec(
        self,
        data: str,
        x: int | None = None,
        y: int | None = None,
        *,
        compact: bool = False,
        ecc_percent: int = 0,
        size: int = 0,
        rotation: int | None = None,
    ) -> SbplLabel:
        """``<2D70>`` Aztec Code (ASCII data). ``ecc_percent`` 0 = default, ``size`` 0 = automatic."""
        _check("ecc_percent", ecc_percent, 0, 99)
        _check("size", size, 0, 32)
        self._prefix(x, y, rotation)
        self._cmd("2D70", f",{1 if compact else 0},{ecc_percent},{size},0,N,")
        return self._cmd("DS", data)

    # ------------------------------------------------------------------ #
    # Graphics and shapes
    # ------------------------------------------------------------------ #
    def graphic(
        self,
        data: bytes,
        width_bytes: int,
        height: int,
        x: int | None = None,
        y: int | None = None,
        *,
        hex_data: bool = False,
    ) -> SbplLabel:
        """``<G>`` monochrome bitmap: ``width_bytes`` bytes (8 dots each) per row, ``height`` rows."""
        _check("width_bytes", width_bytes, 1, 999)
        _check("height", height, 1, 999)
        if len(data) != width_bytes * height:
            raise ValueError(f"expected {width_bytes * height} bytes of bitmap data, got {len(data)}")
        self._prefix(x, y)
        payload = data.hex().upper().encode("ascii") if hex_data else data
        return self._cmd("G", f"{'H' if hex_data else 'B'}{width_bytes:03d}{height:03d}".encode("ascii") + payload)

    def bmp(self, data: bytes | str | Path, x: int | None = None, y: int | None = None) -> SbplLabel:
        """``<GM>`` BMP file print (monochrome BMP, up to 99999 bytes). Accepts the bytes or a file path."""
        content = Path(data).read_bytes() if isinstance(data, (str, Path)) else data
        _check("bmp size", len(content), 1, 99999)
        self._prefix(x, y)
        return self._cmd("GM", f"{len(content):05d},".encode("ascii") + content)

    def line(
        self,
        length: int,
        x: int | None = None,
        y: int | None = None,
        *,
        width: int = 2,
        vertical: bool = False,
    ) -> SbplLabel:
        """``<FW>`` ruled line."""
        _check("width", width, 2, 99)
        _check("length", length, 1, 99999)
        self._prefix(x, y)
        return self._cmd("FW", f"{width:02d}{'V' if vertical else 'H'}{length}")

    def box(
        self,
        width: int,
        height: int,
        x: int | None = None,
        y: int | None = None,
        *,
        thickness: int = 2,
    ) -> SbplLabel:
        """``<FW>`` grid line (rectangle outline) of ``width`` x ``height`` dots."""
        _check("thickness", thickness, 2, 99)
        _check("width", width, 1, 99999)
        _check("height", height, 1, 99999)
        self._prefix(x, y)
        return self._cmd("FW", f"{thickness:02d}{thickness:02d}V{height}H{width}")

    def circle(
        self,
        radius: int,
        x: int | None = None,
        y: int | None = None,
        *,
        thickness: int = 2,
        section: int = 0,
        pattern: int = 0,
    ) -> SbplLabel:
        """``<FC>`` circle. ``section`` 0-8, ``pattern`` 0 solid, 1-3 gray."""
        _check("radius", radius, 5, 999)
        _check("thickness", thickness, 1, 999)
        _check("section", section, 0, 8)
        _check("pattern", pattern, 0, 3)
        self._prefix(x, y)
        return self._cmd("FC", f",{radius},{thickness},{section},{pattern}")

    def triangle(
        self,
        side: int,
        x: int | None = None,
        y: int | None = None,
        *,
        thickness: int = 2,
        base: int | None = None,
        pattern: int = 0,
    ) -> SbplLabel:
        """``<FT>`` triangle."""
        _check("side", side, 10, 2000)
        _check("thickness", thickness, 1, 1000)
        _check("pattern", pattern, 0, 3)
        self._prefix(x, y)
        return self._cmd("FT", f",{side},{thickness},{base if base is not None else side},{pattern}")

    # ------------------------------------------------------------------ #
    # Stored objects
    # ------------------------------------------------------------------ #
    def store_form_overlay(self, number: int, horizontal: int | None = None, vertical: int | None = None) -> SbplLabel:
        """``<&S>`` register the following items as form overlay ``number`` (1-99)."""
        _check("number", number, 1, 99)
        window = f",{horizontal},{vertical}" if horizontal is not None and vertical is not None else ""
        return self._cmd("&S", f",{number:02d}{window}")

    def recall_form_overlay(self, number: int) -> SbplLabel:
        """``<&R>`` print the form overlay ``number`` (1-99)."""
        return self._cmd("&R", f",{_check('number', number, 1, 99):02d}")

    def store_format(self, number: int) -> SbplLabel:
        """``<YS>`` register the following items as format ``number`` (1-999)."""
        return self._cmd("YS", f",{_check('number', number, 1, 999):03d}")

    def recall_format(self, number: int) -> SbplLabel:
        """``<YR>`` print the format ``number`` (1-999)."""
        return self._cmd("YR", f",{_check('number', number, 1, 999):03d}")

    def store_graphic(
        self, number: int, data: bytes, width_bytes: int, height: int, *, hex_data: bool = False
    ) -> SbplLabel:
        """``<GI>`` register a monochrome bitmap as graphic ``number`` (1-999)."""
        _check("number", number, 1, 999)
        _check("width_bytes", width_bytes, 1, 999)
        _check("height", height, 1, 999)
        if len(data) != width_bytes * height:
            raise ValueError(f"expected {width_bytes * height} bytes of bitmap data, got {len(data)}")
        payload = data.hex().upper().encode("ascii") if hex_data else data
        head = f"{'H' if hex_data else 'B'}{width_bytes:03d}{height:03d}{number:03d}".encode("ascii")
        return self._cmd("GI", head + payload)

    def recall_graphic(self, number: int, x: int | None = None, y: int | None = None) -> SbplLabel:
        """``<GR>`` print the registered graphic ``number``."""
        self._prefix(x, y)
        return self._cmd("GR", f"{_check('number', number, 1, 999):03d}")

    def store_bmp(self, number: int, data: bytes | str | Path) -> SbplLabel:
        """``<GT>`` register a BMP file as ``number`` (1-999)."""
        content = Path(data).read_bytes() if isinstance(data, (str, Path)) else data
        _check("number", number, 1, 999)
        _check("bmp size", len(content), 1, 99999)
        return self._cmd("GT", f"{number:03d},{len(content):05d},".encode("ascii") + content)

    def recall_bmp(self, number: int, x: int | None = None, y: int | None = None) -> SbplLabel:
        """``<GC>`` print the registered BMP ``number``."""
        self._prefix(x, y)
        return self._cmd("GC", f"{_check('number', number, 1, 999):03d}")

    # ------------------------------------------------------------------ #
    # RFID (UHF)
    # ------------------------------------------------------------------ #
    def rfid_power(self, write_dbm: float, read_dbm: float | None = None) -> SbplLabel:
        """``<IP5>`` antenna output power in dBm (write and optional read)."""
        write = round(write_dbm * 10)
        _check("write power", write, 0, 999)
        params = f"{write:03d}"
        if read_dbm is not None:
            read = round(read_dbm * 10)
            _check("read power", read, 0, 999)
            params += f",{read:03d}"
        return self._rfid_cmd("IP5", params)

    def rfid_return(self, enabled: bool = True) -> SbplLabel:
        """``<RU>`` enable the EPC/TID result returned by ``DC2 PK`` after the write."""
        return self._rfid_cmd("RU", ",01" if enabled else ",00")

    def write_rfid(
        self,
        epc: str | None = None,
        *,
        user: str | None = None,
        lock: str | None = None,
        access_password: str | None = None,
        kill_password: str | None = None,
        unlock_password: str | None = None,
        pc_bits: int | None = None,
        report: bool = True,
    ) -> SbplLabel:
        """``<IP0>`` write EPC (and optionally USER memory) to a Gen2 tag.

        ``epc`` and ``user`` are HEX strings (EPC in multiples of 4 digits). ``lock`` is the 5-bit
        ``USER,TID,ACCESS,KILL,EPC`` mask. ``report=True`` also enables ``<RU>`` so the write result
        can be read with ``DC2 PK``. It is emitted right after ``<A>``, before the printed items.
        """
        if epc is None and user is None:
            raise ValueError("epc or user data is required")
        if report:
            self.rfid_return(True)
        items = ["e:h"]
        if pc_bits is not None:
            items.append(f"pcw:{_check('pc_bits', pc_bits, 0, 124)}")
        if epc is not None:
            items.append(f"epc:{self._hex(epc, 4, 'epc')}")
        if user is not None:
            items.append(f"usr:{self._hex(user, 4, 'user')}")
        if lock is not None:
            if len(lock) != 5 or set(lock) - {"0", "1"}:
                raise ValueError("lock must be 5 binary digits (USER,TID,ACCESS,KILL,EPC)")
            items.append(f"lck:{lock}")
        for key, value in (("apw", access_password), ("kpw", kill_password), ("psw", unlock_password)):
            if value is not None:
                items.append(f"{key}:{self._hex(value, 8, key, exact=True)}")
        return self._rfid_cmd("IP0", ",".join(items) + ";")

    @staticmethod
    def _hex(value: str, multiple: int, name: str, exact: bool = False) -> str:
        value = value.replace(" ", "").upper()
        valid = value and all(c in "0123456789ABCDEF" for c in value)
        if not valid or (len(value) != multiple if exact else len(value) % multiple):
            kind = f"exactly {multiple}" if exact else f"a multiple of {multiple}"
            raise ValueError(f"{name} must be HEX with {kind} digits")
        return value
