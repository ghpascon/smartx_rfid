"""SATO SBPL wire protocol helpers.

Pure functions and data structures (no I/O) used by :class:`SatoSbplPrinter`:

- control characters and DC2 request builders,
- stream framing (``STX ... ETX``, ``ACK``, ``NAK``),
- parsers for the DC2 replies (status, device info, sensors, label pitch,
  settings, RFID results, file list) and for the ENQ ``Status3``/``Status4`` replies.

Reference: SATO CL4NX Plus / CL6NX Plus Programming Reference (SBPL).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Control characters
# --------------------------------------------------------------------------- #
STX = b"\x02"
ETX = b"\x03"
EOT = b"\x04"
ENQ = b"\x05"
ACK = b"\x06"
CAN = b"\x18"
NAK = b"\x15"
DC2 = b"\x12"
ESC = b"\x1b"

# --------------------------------------------------------------------------- #
# Status tables
# --------------------------------------------------------------------------- #
PRINTER_STATES = {
    0: "standby",
    1: "waiting_dispense",
    2: "analyzing",
    3: "printing",
    4: "offline",
    5: "error",
}
BUFFER_STATES = {0: "available", 1: "near_full", 2: "full"}
RIBBON_STATES = {0: "present", 1: "near_end", 2: "empty", 3: "direct_thermal"}
MEDIA_STATES = {0: "present", 1: "near_end", 2: "empty"}
BATTERY_STATES = {0: "normal", 1: "near_end", 2: "error"}

ERROR_NAMES: dict[int, str] = {
    2: "machine_error",
    3: "memory_error",
    4: "program_error",
    5: "flash_rom_error",
    6: "eeprom_error",
    7: "download_error",
    8: "parity_error",
    9: "over_run",
    10: "framing_error",
    11: "lan_timeout",
    12: "buffer_over",
    13: "head_open",
    14: "paper_end",
    15: "ribbon_end",
    16: "media_error",
    17: "sensor_error",
    18: "print_head_error",
    19: "cover_open",
    20: "memory_card_type_error",
    21: "memory_card_read_write_error",
    22: "memory_card_full",
    23: "memory_card_no_battery",
    24: "ribbon_saver_error",
    25: "cutter_error",
    26: "cutter_sensor_error",
    27: "stacker_full",
    28: "command_error",
    29: "sensor_error_at_power_on",
    30: "rfid_tag_error",
    31: "interface_card_error",
    32: "rewinder_error",
    33: "other_error",
    34: "rfid_control_error",
    35: "head_density_error",
    36: "kanji_data_error",
    37: "calendar_error",
    38: "item_no_error",
    39: "bcc_error",
    40: "cutter_cover_open",
    41: "ribbon_rewind_non_lock",
    42: "communication_timeout",
    43: "lid_latch_open",
    44: "no_media_at_power_on",
    45: "sd_card_access_error",
    46: "sd_card_full",
    47: "head_lift_error",
    48: "head_overheat",
    49: "sntp_error",
    50: "crc_error",
    51: "cutter_motor_error",
    53: "scanner_reading_error",
    54: "scanner_checking_error",
    55: "scanner_connection_error",
    56: "bluetooth_module_error",
    57: "eap_authentication_failed",
    58: "eap_authentication_timeout",
    59: "battery_error",
    60: "low_battery",
    61: "low_battery_charging",
    62: "battery_not_installed",
    63: "battery_temperature_error",
    64: "battery_deterioration",
    65: "motor_temperature_error",
    66: "chassis_temperature_error",
    67: "jam_error",
    68: "sipl_field_full",
    69: "power_off_while_charging",
    70: "wlan_module_error",
    71: "option_inconsistency",
    72: "bad_battery_caution",
    73: "bad_battery_warning",
    74: "power_off_error",
    75: "non_rfid_warning",
    76: "barcode_reader_connection_error",
    77: "barcode_reading_error",
    78: "barcode_verification_start_error",
    79: "barcode_verification_error",
    80: "nfc_module_error",
    81: "nfc_command_error",
    115: "tag_not_found",
    116: "tag_write_error",
    117: "tag_read_error",
    118: "tag_protect_error",
    119: "tag_verify_error",
    120: "tag_lock_error",
    121: "wrong_tid",
    122: "multiple_tags",
    123: "epc_mismatch",
    124: "tag_read_only",
    125: "tag_kind_mismatch",
    126: "lost_handle",
    127: "power_not_enough",
    128: "auto_clone_error",
    129: "mfi_chip_error",
    130: "unsupported_tag",
    131: "password_mismatch",
    132: "exceed_address",
    133: "rtc_module_error",
    134: "sra_motor_error",
}

#: Error codes that are reported in the status but are not errors (online / offline).
NON_ERROR_CODES = frozenset({0, 1})

#: Error codes that originate from the RFID module.
RFID_ERROR_CODES = frozenset({30, 34, 75} | set(range(115, 133)))

# ENQ (Status3/Status4) status characters, grouped by operating state. Inside each
# group the position gives the condition (see ``_ENQ_CONDITIONS``).
_ENQ_GROUPS = {
    "offline": "01234",
    "standby": "ABCDE",
    "printing": "GHIJK",
    "waiting_dispense": "MNOPQ",
    "analyzing": "STUVW",
}
_ENQ_CONDITIONS = (
    {"ribbon": "present", "buffer": "available", "halted": False},
    {"ribbon": "near_end", "buffer": "available", "halted": False},
    {"ribbon": "present", "buffer": "near_full", "halted": False},
    {"ribbon": "near_end", "buffer": "near_full", "halted": False},
    {"ribbon": "present", "buffer": "available", "halted": True},
)
_ENQ_ERRORS = {
    "a": 12,  # buffer over
    "b": 13,  # head open
    "c": 14,  # paper end
    "d": 15,  # ribbon end
    "e": 16,  # media error
    "f": 17,  # sensor error / jam / barcode
    "g": 18,  # head error
    "h": 40,  # cutter open / cover open
    "i": 31,  # card error
    "j": 25,  # cutter error
    "k": 33,  # other
    "l": 26,  # cutter sensor
    "m": 27,  # stacker full
    "o": 30,  # rfid tag error
    "p": 118,  # rfid protect error
    "q": 59,  # battery error
}
_ENQ_LOOKUP: dict[str, tuple[str, dict]] = {}
for _state, _chars in _ENQ_GROUPS.items():
    for _char, _cond in zip(_chars, _ENQ_CONDITIONS):
        _ENQ_LOOKUP[_char] = (_state, _cond)

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PrinterStatus:
    """Decoded printer status (from ``DC2 PG`` or from an ``ENQ`` reply)."""

    state: str = "offline"
    receive_buffer: str = "available"
    ribbon: str = "present"
    media: str = "present"
    battery: str = "normal"
    error_code: int = 0
    remaining: int = 0
    job_id: str | None = None
    job_name: str | None = None
    halted: bool = False
    source: str = "dc2"
    raw: str = field(default="", compare=False)

    @property
    def error(self) -> str | None:
        """Error name, or ``None`` when the printer is not in error."""
        if self.error_code in NON_ERROR_CODES:
            return "unknown" if self.state == "error" else None
        return ERROR_NAMES.get(self.error_code, f"error_{self.error_code}")

    @property
    def has_error(self) -> bool:
        return self.error is not None

    @property
    def is_rfid_error(self) -> bool:
        return self.error_code in RFID_ERROR_CODES

    @property
    def is_busy(self) -> bool:
        """True while the printer is receiving, analyzing or printing."""
        return self.state in ("analyzing", "printing", "waiting_dispense") or self.remaining > 0

    @property
    def is_idle(self) -> bool:
        return self.state == "standby" and self.remaining == 0 and not self.has_error

    @property
    def can_print(self) -> bool:
        """True when the printer can immediately accept (and start) a new job."""
        return self.is_idle and self.receive_buffer == "available" and self.media != "empty" and self.ribbon != "empty"

    @property
    def label(self) -> str:
        """Short status string: ``ready``, ``printing``, ``offline``, ``error: <name>`` ..."""
        if self.has_error:
            return f"error: {self.error}"
        if self.state == "offline":
            return "offline"
        if self.state == "printing":
            return "printing"
        if self.state == "analyzing":
            return "analyzing"
        if self.state == "waiting_dispense":
            return "waiting_dispense"
        if self.media == "empty":
            return "error: media_empty"
        if self.ribbon == "empty":
            return "error: ribbon_empty"
        return "ready"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        data.update(
            error=self.error,
            label=self.label,
            can_print=self.can_print,
            is_busy=self.is_busy,
        )
        return data


@dataclass(frozen=True)
class RfidResult:
    """Result of an RFID write (``DC2 PK``)."""

    success: bool
    error: str  # N: none, E: EPC write error, T: TID read error, A: all
    epc: str | None = None
    tid: str | None = None
    raw: str = field(default="", compare=False)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


# --------------------------------------------------------------------------- #
# DC2 request builders
# --------------------------------------------------------------------------- #


def dc2(name: str, *params: Any) -> bytes:
    """Build a DC2 command, e.g. ``dc2("DB", "CA") -> b"\\x12DB,CA"``."""
    body = name
    if params:
        body += "," + ",".join(str(p) for p in params)
    return DC2 + body.encode("ascii")


def dc2_status() -> bytes:
    return dc2("PG")


def dc2_device_info() -> bytes:
    return dc2("PC")


def dc2_sensors() -> bytes:
    return dc2("PD")


def dc2_label_pitch() -> bytes:
    return dc2("PN")


def dc2_cancel() -> bytes:
    return dc2("PH")


def dc2_rfid_result() -> bytes:
    return dc2("PK")


def dc2_restart() -> bytes:
    return dc2("DC")


def dc2_power_off() -> bytes:
    return dc2("DD")


def dc2_initialize(identifier: str) -> bytes:
    return dc2("DB", identifier)


def dc2_application(identifier: str) -> bytes:
    """Switch the printer application: ``SB`` (SBPL), ``SZ`` (SZPL), ``00`` (AUTO) ..."""
    return dc2("PI", identifier)


def dc2_get_settings(identifier: str | None = None, *items: str) -> bytes:
    """``DC2 PB`` request. Without identifier all sections are returned."""
    body = "PB"
    if identifier:
        body += f",{identifier}"
        if items:
            body += "," + ",".join(items)
    return DC2 + body.encode("ascii") + EOT


def dc2_set_settings(settings: dict[str, dict[str, Any]]) -> bytes:
    """``DC2 PA`` request.

    ``settings`` maps an identifier (``"CA"``, ``"SB"`` ...) to ``{name: value}``.
    """
    sections = []
    for identifier, items in settings.items():
        data = "".join(f"{name}:{value}\r\n" for name, value in items.items())
        sections.append(f"{identifier},{len(data.encode('ascii'))},{data}")
    body = ",".join(sections)
    return DC2 + f"PA,{len(body.encode('ascii'))},{body}".encode("ascii")


def dc2_rfid_read(areas: tuple[str, ...] = ("epc",), option: str = "NO") -> bytes:
    """``DC2 PJ`` (UHF read). ``areas``: epc, tid, user, pc. ``option``: NO, RS, MT, AS, HX."""
    codes = {"epc": "U1", "tid": "U2", "user": "U3", "pc": "U4"}
    try:
        selected = [codes[a.lower()] for a in areas]
    except KeyError as exc:
        raise ValueError(f"invalid RFID area {exc}; use epc, tid, user or pc") from exc
    if not selected:
        raise ValueError("at least one RFID area is required")
    return dc2("PJ", *selected, option)


def dc2_list_files(language: str = "SB", file_type: int = 0) -> bytes:
    return dc2("DF", language, file_type)


def dc2_delete_file(name: str, language: str = "SB", file_type: int = 0) -> bytes:
    return dc2("DH", language, file_type, 0, len(name.encode("ascii")), name)


def dc2_delete_all_files(language: str = "SB", file_type: int = 0) -> bytes:
    return dc2("DH", language, file_type, 1)


def dc2_download_file(name: str, data: bytes, language: str = "SB", file_type: int = 0) -> bytes:
    return dc2("DE", language, file_type, name, len(data)) + b"," + data


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #

MAX_BUFFER = 1024 * 1024


def wrap_frame(data: bytes) -> bytes:
    """Wrap print data with ``STX``/``ETX`` unless it is already framed."""
    if data.startswith(STX) and data.endswith(ETX):
        return data
    return STX + data + ETX


def extract_frames(buffer: bytearray) -> list[tuple[str, bytes]]:
    """Consume complete messages from ``buffer``.

    Returns a list of ``("ack", b"")``, ``("nak", b"")`` or ``("frame", payload)``, where the
    payload is the content between ``STX`` and ``ETX``. Incomplete frames stay in the buffer.
    """
    out: list[tuple[str, bytes]] = []
    while buffer:
        starts = [i for i in (buffer.find(STX), buffer.find(ACK), buffer.find(NAK)) if i >= 0]
        if not starts:
            buffer.clear()
            break
        first = min(starts)
        if first:
            del buffer[:first]
        head = buffer[0]
        if head == ACK[0]:
            out.append(("ack", b""))
            del buffer[0]
        elif head == NAK[0]:
            out.append(("nak", b""))
            del buffer[0]
        else:
            end = buffer.find(ETX, 1)
            if end < 0:
                if len(buffer) > MAX_BUFFER:
                    buffer.clear()
                break
            out.append(("frame", bytes(buffer[1:end])))
            del buffer[: end + 1]
    return out


_PG_RE = re.compile(r"^\d+,PS\d")
_ENQ_RE = re.compile(r"^(?P<id>[ \d*]{2})(?P<status>[0-9A-Za-z!-/@])(?P<remaining>\d{6})(?P<job>.{16})?$", re.S)


def is_dc2_status_frame(payload: bytes) -> bool:
    return bool(_PG_RE.match(payload.decode("ascii", "ignore")))


def is_enq_status_frame(payload: bytes) -> bool:
    text = payload.decode("ascii", "ignore")
    return len(text) in (9, 25) and _ENQ_RE.match(text) is not None


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #


def _split_size(payload: str) -> str:
    """Drop the leading ``<size>,`` of a DC2 reply."""
    head, sep, rest = payload.partition(",")
    return rest if sep and head.strip().isdigit() else payload


def parse_dc2_status(payload: bytes | str) -> PrinterStatus:
    """Parse the ``DC2 PG`` reply, e.g. ``32,PS0,RS0,RE0,PE0,EN00,BT0,Q000000``."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    values: dict[str, str] = {}
    for item in _split_size(text).split(","):
        match = re.match(r"^(PS|RS|RE|PE|EN|BT|Q)(\d+)$", item.strip())
        if match:
            values[match.group(1)] = match.group(2)
    if "PS" not in values:
        raise ValueError(f"invalid status reply: {text!r}")
    return PrinterStatus(
        state=PRINTER_STATES.get(int(values["PS"]), "unknown"),
        receive_buffer=BUFFER_STATES.get(int(values.get("RS", 0)), "unknown"),
        ribbon=RIBBON_STATES.get(int(values.get("RE", 0)), "unknown"),
        media=MEDIA_STATES.get(int(values.get("PE", 0)), "unknown"),
        battery=BATTERY_STATES.get(int(values.get("BT", 0)), "unknown"),
        error_code=int(values.get("EN", 0)),
        remaining=int(values.get("Q", 0)),
        source="dc2",
        raw=text,
    )


def parse_enq_status(payload: bytes | str) -> PrinterStatus:
    """Parse the ``ENQ`` reply of the Status3 / Status4 protocols.

    Payload (between STX and ETX): ``ID(2) STATUS(1) REMAINING(6) [JOB NAME(16)]``.
    """
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    match = _ENQ_RE.match(text)
    if not match or len(text) not in (9, 25):
        raise ValueError(f"invalid ENQ status reply: {text!r}")
    char = match.group("status")
    job_id = match.group("id").strip() or None
    job_name = (match.group("job") or "").strip() or None
    remaining = int(match.group("remaining"))

    if char in _ENQ_ERRORS:
        error_code = _ENQ_ERRORS[char]
        return PrinterStatus(
            state="error",
            error_code=error_code,
            remaining=remaining,
            job_id=job_id,
            job_name=job_name,
            source="enq",
            raw=text,
        )
    if char not in _ENQ_LOOKUP:
        raise ValueError(f"unknown ENQ status character: {char!r}")
    state, cond = _ENQ_LOOKUP[char]
    return PrinterStatus(
        state=state,
        receive_buffer=cond["buffer"],
        ribbon=cond["ribbon"],
        media="near_end" if cond["ribbon"] == "near_end" else "present",
        error_code=1 if state == "offline" else 0,
        remaining=remaining,
        job_id=job_id,
        job_name=job_name,
        halted=cond["halted"],
        source="enq",
        raw=text,
    )


def parse_key_values(payload: bytes | str) -> dict[str, str]:
    """Parse ``NAME:VALUE[CR][LF]`` lists (``DC2 PC`` and the items of ``DC2 PB``)."""
    text = payload.decode("latin-1") if isinstance(payload, bytes) else payload
    result: dict[str, str] = {}
    for line in text.replace("\r", "").split("\n"):
        name, sep, value = line.partition(":")
        if sep and name.strip():
            result[name.strip()] = value.strip()
    return result


def parse_device_info(payload: bytes | str) -> dict[str, str]:
    """Parse the ``DC2 PC`` reply (``<size>,NAME:VALUE\\r\\n...``)."""
    text = payload.decode("latin-1") if isinstance(payload, bytes) else payload
    return parse_key_values(_split_size(text))


def parse_sensors(payload: bytes | str) -> dict[str, str]:
    """Parse the ``DC2 PD`` reply (``<size>,IM:0.2/SL1.5,GAP:0.9/SL1.0,...``)."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    result: dict[str, str] = {}
    for item in _split_size(text).split(","):
        name, sep, value = item.partition(":")
        if sep and name.strip():
            result[name.strip()] = value.strip()
    return result


def parse_label_pitch(payload: bytes | str) -> dict[str, int]:
    """Parse the ``DC2 PN`` reply (``10,203,002172``) into ``{"dpi", "pitch_dots"}``."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    parts = text.split(",")
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        raise ValueError(f"invalid label pitch reply: {text!r}")
    return {"dpi": int(parts[1]), "pitch_dots": int(parts[2])}


def parse_settings(payload: bytes | str) -> dict[str, dict[str, str]]:
    """Parse the ``DC2 PB`` reply (``<size>,ID,<size>,data,ID,<size>,data...``)."""
    text = payload.decode("latin-1") if isinstance(payload, bytes) else payload
    rest = _split_size(text)
    sections: dict[str, dict[str, str]] = {}
    while rest:
        identifier, sep, rest = rest.partition(",")
        size_text, sep2, rest = rest.partition(",")
        if not sep or not sep2 or not size_text.strip().isdigit():
            break
        size = int(size_text)
        data, rest = rest[:size], rest[size:]
        sections[identifier.strip()] = parse_key_values(data)
        rest = rest.lstrip(",")
    return sections


def parse_rfid_result(payload: bytes | str) -> RfidResult:
    """Parse the ``DC2 PK`` reply (``25,1,N,ID:E200680612345678\\r\\n``)."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    parts = _split_size(text).split(",", 2)
    if len(parts) < 3 or parts[0] not in ("0", "1"):
        raise ValueError(f"invalid RFID result: {text!r}")
    epc = tid = None
    for item in parts[2].replace("\r", "").replace("\n", "").split(","):
        name, _, value = item.partition(":")
        if name == "EP":
            epc = value or None
        elif name == "ID":
            tid = value or None
    return RfidResult(success=parts[0] == "1", error=parts[1], epc=epc, tid=tid, raw=text)


def parse_rfid_read(payload: bytes | str) -> dict[str, Any]:
    """Parse the ``DC2 PJ`` reply into ``{"epc", "tid", "user", "pc", "rssi", "temperature", "error"}``."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    body = _split_size(text)
    result: dict[str, Any] = {"error": "EPC_Tag_Error" in body}
    names = {
        "EP": "epc",
        "TI": "tid",
        "UD": "user",
        "PC": "pc",
        "ep": "epc",
        "ud": "user",
        "RS": "rssi",
        "MT": "temperature",
    }
    for item in body.split(","):
        name, sep, value = item.partition(":")
        key = names.get(name.strip())
        if sep and key:
            result[key] = value.strip() or None
    return result


def parse_file_list(payload: bytes | str) -> list[str]:
    """Parse the ``DC2 DF`` reply (``xxxx,name1,name2`` or ``0``)."""
    text = payload.decode("ascii", "ignore") if isinstance(payload, bytes) else payload
    if text.strip() == "0":
        return []
    return [name.strip() for name in _split_size(text).split(",") if name.strip()]
