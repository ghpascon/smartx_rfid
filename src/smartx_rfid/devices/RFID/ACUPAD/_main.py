import asyncio
import ctypes
import logging
from pathlib import Path
import shutil
import subprocess
import time
from smartx_rfid.schemas import TagSchema
import serial.tools.list_ports


from smartx_rfid.devices._base import DeviceBase


class _TMR_Reader(ctypes.Structure):
    pass


class _TMR_uint8List(ctypes.Structure):
    _fields_ = [
        ("list", ctypes.POINTER(ctypes.c_uint8)),
        ("max", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
    ]


class _TMR_GpioPin(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint8),
        ("high", ctypes.c_bool),
        ("bGPIStsTagRdMeta", ctypes.c_bool),
        ("output", ctypes.c_bool),
    ]


class _TMR_GEN2_TagData(ctypes.Structure):
    _fields_ = [
        ("pcByteCount", ctypes.c_uint8),
        ("pc", ctypes.c_uint8 * 6),
    ]


class _TMR_SR_GEN2_QStatic(ctypes.Structure):
    _fields_ = [("initialQ", ctypes.c_uint8)]


class _TMR_SR_GEN2_QU(ctypes.Union):
    _fields_ = [("staticQ", _TMR_SR_GEN2_QStatic)]


class _TMR_SR_GEN2_Q(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("u", _TMR_SR_GEN2_QU),
    ]


class _TMR_GEN2_TagReadData(ctypes.Structure):
    _fields_ = [
        ("q", _TMR_SR_GEN2_Q),
        ("lf", ctypes.c_int),
        ("target", ctypes.c_int),
    ]


class _TMR_TagDataU(ctypes.Union):
    _fields_ = [("gen2", _TMR_GEN2_TagData)]


class _TMR_TagData(ctypes.Structure):
    _fields_ = [
        ("epc", ctypes.c_uint8 * 62),
        ("protocol", ctypes.c_int),
        ("epcByteCount", ctypes.c_uint8),
        ("xepc", ctypes.c_uint8 * 2),
        ("crc", ctypes.c_uint16),
        ("u", _TMR_TagDataU),
    ]


class _TMR_TagReadDataU(ctypes.Union):
    _fields_ = [("gen2", _TMR_GEN2_TagReadData)]


class _TMR_TagReadData(ctypes.Structure):
    _fields_ = [
        ("tag", _TMR_TagData),
        ("u", _TMR_TagReadDataU),
        ("metadataFlags", ctypes.c_uint16),
        ("phase", ctypes.c_uint16),
        ("antenna", ctypes.c_uint8),
        ("gpio", _TMR_GpioPin * 16),
        ("gpioCount", ctypes.c_uint8),
        ("readCount", ctypes.c_uint32),
        ("rssi", ctypes.c_int32),
        ("frequency", ctypes.c_uint32),
        ("brandIdentifier", ctypes.c_uint8 * 2),
        ("identify_impinj_tag_chip_on", ctypes.c_bool),
        ("impinj_tag_chip_id", ctypes.c_uint8),
        ("timestampLow", ctypes.c_uint32),
        ("timestampHigh", ctypes.c_uint32),
        ("data", _TMR_uint8List),
        ("epcMemData", _TMR_uint8List),
        ("tidMemData", _TMR_uint8List),
        ("userMemData", _TMR_uint8List),
        ("reservedMemData", _TMR_uint8List),
        ("epcMemError", ctypes.c_int8),
        ("tidMemError", ctypes.c_int8),
        ("userMemError", ctypes.c_int8),
        ("reservedMemError", ctypes.c_int8),
        ("dspMicros", ctypes.c_uint32),
        ("tagType", ctypes.c_uint64),
        ("_dataList", ctypes.c_uint8 * 128),
        ("_epcMemDataList", ctypes.c_uint8 * 128),
        ("_tidMemDataList", ctypes.c_uint8 * 128),
        ("_userMemDataList", ctypes.c_uint8 * 128),
        ("_reservedMemDataList", ctypes.c_uint8 * 128),
        ("reader", ctypes.POINTER(_TMR_Reader)),
    ]


class _TMR_StopOnTagCount(ctypes.Structure):
    _fields_ = [
        ("stopNTriggerStatus", ctypes.c_bool),
        ("noOfTags", ctypes.c_uint32),
    ]


class _TMR_GPITriggerRead(ctypes.Structure):
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("gpiList", _TMR_uint8List),
    ]


class _TMR_SimpleReadPlan(ctypes.Structure):
    _fields_ = [
        ("antennas", _TMR_uint8List),
        ("protocol", ctypes.c_int),
        ("filter", ctypes.c_void_p),
        ("tagop", ctypes.c_void_p),
        ("useFastSearch", ctypes.c_bool),
        ("stopOnCount", _TMR_StopOnTagCount),
        ("triggerRead", _TMR_GPITriggerRead),
    ]


class _TMR_ReadPlan(ctypes.Structure):
    pass


class _TMR_MultiReadPlan(ctypes.Structure):
    _fields_ = [
        ("plans", ctypes.POINTER(ctypes.POINTER(_TMR_ReadPlan))),
        ("totalWeight", ctypes.c_uint32),
        ("planCount", ctypes.c_uint8),
    ]


class _TMR_ReadPlanU(ctypes.Union):
    _fields_ = [
        ("simple", _TMR_SimpleReadPlan),
        ("multi", _TMR_MultiReadPlan),
    ]


_TMR_ReadPlan._fields_ = [
    ("type", ctypes.c_int),
    ("weight", ctypes.c_uint32),
    ("enableAutonomousRead", ctypes.c_bool),
    ("u", _TMR_ReadPlanU),
]


class _TMR_RegionList(ctypes.Structure):
    _fields_ = [
        ("list", ctypes.POINTER(ctypes.c_int)),
        ("max", ctypes.c_uint8),
        ("len", ctypes.c_uint8),
    ]


class _TMR_TagOpBuffer(ctypes.Structure):
    # Opaque buffer large enough to hold TMR_TagOp across Mercury builds.
    _fields_ = [("raw", ctypes.c_uint8 * 4096)]


class ACUPAD(DeviceBase):
    """
    RFID handler based on local Mercury C API (ctypes).

    Features:
    - Automatic port detection by VID/PID (AUTO mode)
    - Automatic reconnection
    - Inventory loop using Mercury C API read calls
    - Local Mercury C API backend from ./mercury_api
    """

    TMR_SUCCESS = 0
    TMR_ERROR_NO_TAGS_FOUND = (2 << 24) | 0x400
    TMR_ERROR_NO_TAGS = (3 << 24) | 8
    TMR_ERROR_INVALID_ANTENNA_CONFIG = (2 << 24) | 0x507
    TMR_GEN2_BANK_TID = 0x2

    TMR_PARAM_ANTENNA_CHECKPORT = 7
    TMR_PARAM_ANTENNA_PORTLIST = 8
    TMR_PARAM_ANTENNA_CONNECTEDPORTLIST = 9
    TMR_PARAM_ANTENNA_PORTSWITCHGPOS = 10
    TMR_PARAM_GPIO_OUTPUTLIST = 16
    TMR_PARAM_GEN2_TAGENCODING = 19
    TMR_PARAM_READ_PLAN = 40
    TMR_PARAM_GEN2_SESSION = 20
    TMR_PARAM_RADIO_READPOWER = 43
    TMR_PARAM_TAGOP_PROTOCOL = 53
    TMR_PARAM_REGION_ID = 61
    TMR_PARAM_REGION_SUPPORTEDREGIONS = 62
    TMR_PARAM_METADATAFLAG = 93

    TMR_REGION_NONE = 0
    TMR_TAG_PROTOCOL_GEN2 = 0x05
    TMR_GEN2_MILLER_M_4 = 4

    TMR_TRD_METADATA_FLAG_READCOUNT = 0x0001
    TMR_TRD_METADATA_FLAG_RSSI = 0x0002
    TMR_TRD_METADATA_FLAG_ANTENNAID = 0x0004
    TMR_TRD_METADATA_FLAG_TIMESTAMP = 0x0010
    TMR_TRD_METADATA_FLAG_PROTOCOL = 0x0040
    TMR_TRD_METADATA_FLAG_DATA = 0x0080

    def __init__(
        self,
        name: str = "ACUPAD",
        port: str = "AUTO",
        baudrate: int = 115200,
        vid: int = 1003,
        pid: int = 8192,
        reconnection_time: int = 3,
        start_reading: bool = True,
        session: int = 0,
        read_power: int = 24,
        read_rssi: int = 0,
        active_ant: list[int] = [1],
        read_tid: bool = True,
        tid_byte_count: int = 12,
        beep: bool = False,
        beep_gpo: int = 2,
        beep_duration_ms: int = 100,
        beep_min_interval_ms: int = 100,
        antenna_port_switch_gpos: list[int] | int | None = 1,
        gen2_tag_encoding: int = TMR_GEN2_MILLER_M_4,
        auto_build_mercury: bool = True,
        **kwargs,
    ):
        DeviceBase.__init__(self)
        self.name = name
        self.device_type = "rfid"

        self.port = port
        self.baudrate = baudrate
        self.vid = vid
        self.pid = pid
        self.reconnection_time = reconnection_time

        self.is_auto = self.port == "AUTO"

        self.is_connected = False
        self.is_reading = False
        self.serial_number = None
        self.effective_antennas: list[int] = []

        self._read_timeout_ms = 50
        self._idle_sleep = 0.05
        self._reader = None
        self._active_port = None
        self._last_beep_at = 0.0
        self._beep_is_high = False
        self._beep_until = 0.0
        self._embedded_tid_tagop: _TMR_TagOpBuffer | None = None

        if not isinstance(start_reading, bool):
            start_reading = True
        self.start_reading = start_reading

        if session not in [0, 1, 2, 3]:
            session = 1
        self.session = session

        if not isinstance(read_power, int):
            read_power = 22
        if read_power < 10 or read_power > 30:
            read_power = 22
        self.read_power = read_power

        if not isinstance(read_rssi, int):
            read_rssi = 0
        if read_rssi < 20 or read_rssi > 99:
            read_rssi = 0

        self.read_rssi = read_rssi

        if not isinstance(read_tid, bool):
            read_tid = False
        self.read_tid = read_tid

        if not isinstance(tid_byte_count, int):
            tid_byte_count = 12
        if tid_byte_count < 2:
            tid_byte_count = 2
        if tid_byte_count > 32:
            tid_byte_count = 32
        self.tid_byte_count = tid_byte_count

        self.active_ant = self._normalize_antennas(active_ant)

        if not isinstance(beep, bool):
            beep = False
        self.beep = beep

        if not isinstance(beep_gpo, int) or beep_gpo < 1:
            beep_gpo = 2
        self.beep_gpo = beep_gpo

        if not isinstance(beep_duration_ms, int):
            beep_duration_ms = 100
        if beep_duration_ms < 10:
            beep_duration_ms = 10
        if beep_duration_ms > 1000:
            beep_duration_ms = 1000
        self.beep_duration_ms = beep_duration_ms

        if not isinstance(beep_min_interval_ms, int):
            beep_min_interval_ms = 100
        if beep_min_interval_ms < 50:
            beep_min_interval_ms = 50
        if beep_min_interval_ms > 10_000:
            beep_min_interval_ms = 10_000
        self.beep_min_interval_ms = beep_min_interval_ms

        self.antenna_port_switch_gpos = self._normalize_antennas(antenna_port_switch_gpos)

        if not isinstance(gen2_tag_encoding, int):
            gen2_tag_encoding = self.TMR_GEN2_MILLER_M_4
        if gen2_tag_encoding < 0 or gen2_tag_encoding > 3:
            gen2_tag_encoding = self.TMR_GEN2_MILLER_M_4
        self.gen2_tag_encoding = gen2_tag_encoding

        self.backend = "mercury_c_api"
        self._mercury_lib = None
        self._configure_mercury_backend(auto_build_mercury=auto_build_mercury)
        self._configure_mercury_symbols()

    def _configure_mercury_backend(
        self,
        auto_build_mercury: bool,
    ):
        sdk_dir = Path(__file__).resolve().parent / "mercury_api"
        loaded = self._load_mercury_library(sdk_dir=sdk_dir)

        if loaded is None and auto_build_mercury:
            if self._build_mercury_library(sdk_dir):
                loaded = self._load_mercury_library(sdk_dir=sdk_dir)

        if loaded is None:
            raise RuntimeError(
                "Mercury C API not available in ./mercury_api. Build failed or library file was not generated."
            )

        self._mercury_lib = loaded
        self.backend = "mercury_c_api"
        logging.info("Mercury C API loaded from local SDK path: %s", sdk_dir)

    def _configure_mercury_symbols(self):
        lib = self._mercury_lib

        def _resolve_symbol(*names: str):
            for name in names:
                symbol = getattr(lib, name, None)
                if symbol is not None:
                    return symbol
            raise AttributeError(f"Missing Mercury symbol. Tried: {', '.join(names)}")

        self._TMR_create_alloc = lib.TMR_create_alloc
        self._TMR_create_alloc.argtypes = [
            ctypes.POINTER(ctypes.POINTER(_TMR_Reader)),
            ctypes.c_char_p,
        ]
        self._TMR_create_alloc.restype = ctypes.c_uint32

        self._TMR_connect = _resolve_symbol("TMR_connect", "TMR_SR_connect")
        self._TMR_connect.argtypes = [ctypes.POINTER(_TMR_Reader)]
        self._TMR_connect.restype = ctypes.c_uint32

        self._TMR_destroy = _resolve_symbol("TMR_destroy", "TMR_SR_destroy")
        self._TMR_destroy.argtypes = [ctypes.POINTER(_TMR_Reader)]
        self._TMR_destroy.restype = ctypes.c_uint32

        self._TMR_read = _resolve_symbol("TMR_read", "TMR_SR_read")
        self._TMR_read.argtypes = [ctypes.POINTER(_TMR_Reader), ctypes.c_uint32, ctypes.POINTER(ctypes.c_int32)]
        self._TMR_read.restype = ctypes.c_uint32

        self._TMR_hasMoreTags = _resolve_symbol("TMR_hasMoreTags", "TMR_SR_hasMoreTags")
        self._TMR_hasMoreTags.argtypes = [ctypes.POINTER(_TMR_Reader)]
        self._TMR_hasMoreTags.restype = ctypes.c_uint32

        self._TMR_getNextTag = _resolve_symbol("TMR_getNextTag", "TMR_SR_getNextTag")
        self._TMR_getNextTag.argtypes = [ctypes.POINTER(_TMR_Reader), ctypes.POINTER(_TMR_TagReadData)]
        self._TMR_getNextTag.restype = ctypes.c_uint32

        self._TMR_readTagMemBytes = _resolve_symbol("TMR_readTagMemBytes", "TMR_SR_readTagMemBytes")
        self._TMR_readTagMemBytes.argtypes = [
            ctypes.POINTER(_TMR_Reader),
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint8),
        ]
        self._TMR_readTagMemBytes.restype = ctypes.c_uint32

        self._TMR_paramSet = lib.TMR_paramSet
        self._TMR_paramSet.argtypes = [ctypes.POINTER(_TMR_Reader), ctypes.c_int, ctypes.c_void_p]
        self._TMR_paramSet.restype = ctypes.c_uint32

        self._TMR_paramGet = lib.TMR_paramGet
        self._TMR_paramGet.argtypes = [ctypes.POINTER(_TMR_Reader), ctypes.c_int, ctypes.c_void_p]
        self._TMR_paramGet.restype = ctypes.c_uint32

        self._TMR_RP_init_simple = lib.TMR_RP_init_simple
        self._TMR_RP_init_simple.argtypes = [
            ctypes.POINTER(_TMR_ReadPlan),
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        self._TMR_RP_init_simple.restype = ctypes.c_uint32

        self._TMR_TRD_init = getattr(lib, "TMR_TRD_init", None)
        if self._TMR_TRD_init is not None:
            self._TMR_TRD_init.argtypes = [ctypes.POINTER(_TMR_TagReadData)]
            self._TMR_TRD_init.restype = ctypes.c_uint32

        self._TMR_TagOp_init_GEN2_ReadData = getattr(lib, "TMR_TagOp_init_GEN2_ReadData", None)
        if self._TMR_TagOp_init_GEN2_ReadData is not None:
            self._TMR_TagOp_init_GEN2_ReadData.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_uint32,
                ctypes.c_uint8,
            ]
            self._TMR_TagOp_init_GEN2_ReadData.restype = ctypes.c_uint32

        self._TMR_gpoSet = getattr(lib, "TMR_gpoSet", None)
        if self._TMR_gpoSet is None:
            self._TMR_gpoSet = getattr(lib, "TMR_SR_gpoSet", None)
        if self._TMR_gpoSet is not None:
            self._TMR_gpoSet.argtypes = [
                ctypes.POINTER(_TMR_Reader),
                ctypes.c_uint8,
                ctypes.POINTER(_TMR_GpioPin),
            ]
            self._TMR_gpoSet.restype = ctypes.c_uint32

        self._TMR_strerror = getattr(lib, "TMR_strerror", None)
        if self._TMR_strerror is not None:
            self._TMR_strerror.argtypes = [ctypes.c_uint32]
            self._TMR_strerror.restype = ctypes.c_char_p

    def _library_candidates(self, sdk_dir: Path) -> list[Path]:
        candidates: list[Path] = []

        candidates.extend(
            [
                sdk_dir / "libmercuryapi.so.1",
                sdk_dir / "libmercuryapi.so",
                sdk_dir / "build" / "libmercuryapi.so.1",
                sdk_dir / "build" / "libmercuryapi.so",
            ]
        )
        return candidates

    def _load_mercury_library(self, sdk_dir: Path):
        for path in self._library_candidates(sdk_dir=sdk_dir):
            if not path.exists():
                continue
            try:
                return ctypes.CDLL(str(path))
            except OSError as exc:
                logging.warning("Failed to load Mercury library %s: %s", path, exc)
        return None

    def _build_mercury_library(self, sdk_dir: Path) -> bool:
        make_bin = shutil.which("make")
        if make_bin is None:
            logging.warning("Cannot build Mercury C API: 'make' not found.")
            return False

        if not sdk_dir.exists():
            logging.warning("Cannot build Mercury C API: SDK path does not exist: %s", sdk_dir)
            return False

        cmd = [make_bin, "TMR_ENABLE_SERIAL_READER_ONLY=1", "SKIP_SAMPLES=1"]
        proc = subprocess.run(cmd, cwd=sdk_dir, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            logging.info("Local Mercury C API build finished successfully.")
            return True

        logging.warning("Mercury C API build failed with exit code %s", proc.returncode)
        if proc.stdout:
            logging.warning("Mercury build stdout:\n%s", proc.stdout.strip())
        if proc.stderr:
            logging.warning("Mercury build stderr:\n%s", proc.stderr.strip())
        return False

    def _reader_uri(self, port: str) -> str:
        if "://" in port:
            return port
        if port.startswith("/"):
            return f"tmr://{port}"
        return f"tmr:///{port}"

    def _status_to_text(self, status: int) -> str:
        if self._TMR_strerror is not None:
            try:
                msg = self._TMR_strerror(ctypes.c_uint32(status))
                if msg:
                    return msg.decode(errors="ignore")
            except Exception:
                pass
        return f"status={status}"

    def _ensure_success(self, status: int, operation: str):
        if status != self.TMR_SUCCESS:
            raise RuntimeError(f"{operation} failed: {self._status_to_text(status)}")

    def _resolve_auto_port(self) -> str | None:
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if p.vid == self.vid and p.pid == self.pid:
                return p.device
        return None

    def _normalize_antennas(self, active_ant) -> list[int]:
        if isinstance(active_ant, str):
            active_ant = [p for p in active_ant.replace(";", ",").split(",") if p.strip()]
        elif isinstance(active_ant, int):
            active_ant = [active_ant]
        elif not isinstance(active_ant, (list, tuple, set)):
            active_ant = [1]

        normalized = []
        for ant in active_ant:
            try:
                ant_i = int(str(ant).strip())
            except Exception:
                continue
            if ant_i > 0 and ant_i not in normalized:
                normalized.append(ant_i)

        return normalized if normalized else [1]

    def _is_invalid_antenna_status(self, status: int) -> bool:
        if status == self.TMR_ERROR_INVALID_ANTENNA_CONFIG:
            return True
        msg = self._status_to_text(status).lower()
        return "antenna" in msg and "invalid" in msg

    def _get_uint8_list_param(self, reader, param_id: int, size: int = 16) -> list[int]:
        buffer = (ctypes.c_uint8 * size)()
        values = _TMR_uint8List(
            list=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)),
            max=size,
            len=0,
        )
        status = self._TMR_paramGet(reader, param_id, ctypes.byref(values))
        if status != self.TMR_SUCCESS:
            return []
        length = min(int(values.len), size)
        return [int(buffer[i]) for i in range(length) if int(buffer[i]) > 0]

    def _bytes_from_uint8_list(self, uint8_list: _TMR_uint8List) -> bytes:
        if not uint8_list.list:
            return b""
        max_len = int(uint8_list.max) if int(uint8_list.max) > 0 else int(uint8_list.len)
        size = min(int(uint8_list.len), max_len)
        if size <= 0:
            return b""
        return bytes(uint8_list.list[i] for i in range(size))

    def _extract_tid_from_trd(self, trd: _TMR_TagReadData) -> str | None:
        if not self.read_tid:
            return None

        # Embedded tagop returns payload in trd.data, with len in bits.
        if int(trd.data.len) == 0x8000:
            return None

        if trd.data.list and int(trd.data.len) > 0:
            data_len_bytes = int(trd.data.len) // 8
            if data_len_bytes > 0:
                tid_raw = bytes(trd.data.list[i] for i in range(data_len_bytes))
                if tid_raw:
                    return tid_raw[: self.tid_byte_count].hex().lower()

        # Some firmwares also expose embedded TID in tidMemData.
        tid_mem = self._bytes_from_uint8_list(trd.tidMemData)
        if tid_mem:
            return tid_mem[: self.tid_byte_count].hex().lower()

        return None

    def _set_read_plan(self, reader, antennas: list[int]) -> int:
        antenna_count = len(antennas)
        antenna_list = None
        if antenna_count > 0:
            antenna_list = (ctypes.c_uint8 * antenna_count)(*antennas)

            # Keep reader antenna port list aligned with requested plan.
            port_list = _TMR_uint8List(
                list=ctypes.cast(antenna_list, ctypes.POINTER(ctypes.c_uint8)),
                max=antenna_count,
                len=antenna_count,
            )
            self._TMR_paramSet(reader, self.TMR_PARAM_ANTENNA_PORTLIST, ctypes.byref(port_list))

        read_plan = _TMR_ReadPlan()
        status = self._TMR_RP_init_simple(
            ctypes.byref(read_plan),
            ctypes.c_uint8(antenna_count),
            antenna_list,
            ctypes.c_int(self.TMR_TAG_PROTOCOL_GEN2),
            ctypes.c_uint32(1000),
        )
        if status != self.TMR_SUCCESS:
            return status

        self._embedded_tid_tagop = None
        if self.read_tid and self._TMR_TagOp_init_GEN2_ReadData is not None:
            # Read TID as embedded op in same inventory cycle (no second command per tag).
            tid_words = max(1, min(64, (self.tid_byte_count + 1) // 2))
            tagop = _TMR_TagOpBuffer()
            status = self._TMR_TagOp_init_GEN2_ReadData(
                ctypes.byref(tagop),
                ctypes.c_int(self.TMR_GEN2_BANK_TID),
                ctypes.c_uint32(0),
                ctypes.c_uint8(tid_words),
            )
            if status == self.TMR_SUCCESS:
                self._embedded_tid_tagop = tagop
                read_plan.u.simple.tagop = ctypes.cast(ctypes.byref(self._embedded_tid_tagop), ctypes.c_void_p).value
            else:
                logging.warning(
                    "%s - Could not init embedded TID tagop: %s",
                    self.name,
                    self._status_to_text(status),
                )
        elif self.read_tid:
            logging.warning("%s - Embedded TID tagop symbol not available in Mercury library.", self.name)

        return self._TMR_paramSet(reader, self.TMR_PARAM_READ_PLAN, ctypes.byref(read_plan))

    def _set_antenna_port_switch_gpos(self, reader):
        gpos = [int(g) for g in self.antenna_port_switch_gpos if int(g) > 0]
        if not gpos:
            return

        gpo_count = len(gpos)
        gpo_array = (ctypes.c_uint8 * gpo_count)(*gpos)
        gpo_list = _TMR_uint8List(
            list=ctypes.cast(gpo_array, ctypes.POINTER(ctypes.c_uint8)),
            max=gpo_count,
            len=gpo_count,
        )
        status = self._TMR_paramSet(reader, self.TMR_PARAM_ANTENNA_PORTSWITCHGPOS, ctypes.byref(gpo_list))
        if status != self.TMR_SUCCESS:
            logging.warning(
                "%s - Could not set antenna port switch GPOs %s: %s",
                self.name,
                gpos,
                self._status_to_text(status),
            )
            return

        logging.info("%s - antenna mux configured on GPOs: %s", self.name, gpos)

    def _configure_beep_gpo(self, reader):
        if not self.beep:
            return

        if self._TMR_gpoSet is None:
            logging.warning("%s - beep requested but gpoSet symbol is unavailable.", self.name)
            return

        output_gpos = []
        for gpo in self.antenna_port_switch_gpos + [self.beep_gpo]:
            gpo_i = int(gpo)
            if gpo_i > 0 and gpo_i not in output_gpos:
                output_gpos.append(gpo_i)

        gpo_out_count = len(output_gpos)
        gpo_out = (ctypes.c_uint8 * gpo_out_count)(*output_gpos)
        gpo_out_list = _TMR_uint8List(
            list=ctypes.cast(gpo_out, ctypes.POINTER(ctypes.c_uint8)),
            max=gpo_out_count,
            len=gpo_out_count,
        )
        status = self._TMR_paramSet(reader, self.TMR_PARAM_GPIO_OUTPUTLIST, ctypes.byref(gpo_out_list))
        if status != self.TMR_SUCCESS:
            logging.warning(
                "%s - Could not configure GPIO output list %s: %s",
                self.name,
                output_gpos,
                self._status_to_text(status),
            )
            return

        pin = _TMR_GpioPin(id=self.beep_gpo, high=False, bGPIStsTagRdMeta=False, output=True)
        status = self._TMR_gpoSet(reader, ctypes.c_uint8(1), ctypes.byref(pin))
        if status != self.TMR_SUCCESS:
            logging.warning(
                "%s - Could not initialize beep GPO %s: %s", self.name, self.beep_gpo, self._status_to_text(status)
            )

    def _beep_set_level(self, high: bool) -> bool:
        if self._reader is None or self._TMR_gpoSet is None:
            return False

        pin = _TMR_GpioPin(id=self.beep_gpo, high=high, bGPIStsTagRdMeta=False, output=True)
        status = self._TMR_gpoSet(self._reader, ctypes.c_uint8(1), ctypes.byref(pin))
        if status != self.TMR_SUCCESS:
            logging.warning(
                "%s - beep %s failed: %s",
                self.name,
                "ON" if high else "OFF",
                self._status_to_text(status),
            )
            return False
        return True

    def _service_beep_state(self, now: float | None = None):
        if not self.beep:
            return
        if now is None:
            now = time.monotonic()

        if self._beep_is_high and now >= self._beep_until:
            if self._beep_set_level(False):
                self._beep_is_high = False

    def _trigger_beep_non_blocking(self):
        if not self.beep:
            return

        now = time.monotonic()
        self._service_beep_state(now)

        min_interval = self.beep_min_interval_ms / 1000.0
        if (now - self._last_beep_at) < min_interval:
            return

        if self._beep_is_high:
            return

        if self._beep_set_level(True):
            self._beep_is_high = True
            self._beep_until = now + (self.beep_duration_ms / 1000.0)
            self._last_beep_at = now

    def _configure_reader_params(self, reader):
        region = ctypes.c_int(0)
        self._ensure_success(
            self._TMR_paramGet(reader, self.TMR_PARAM_REGION_ID, ctypes.byref(region)),
            "TMR_paramGet(/reader/region/id)",
        )

        if region.value == self.TMR_REGION_NONE:
            regions_buffer = (ctypes.c_int * 32)()
            regions = _TMR_RegionList(
                list=ctypes.cast(regions_buffer, ctypes.POINTER(ctypes.c_int)),
                max=32,
                len=0,
            )
            self._ensure_success(
                self._TMR_paramGet(
                    reader,
                    self.TMR_PARAM_REGION_SUPPORTEDREGIONS,
                    ctypes.byref(regions),
                ),
                "TMR_paramGet(/reader/region/supportedRegions)",
            )
            if regions.len == 0:
                raise RuntimeError("Reader returned no supported regions.")
            region = ctypes.c_int(regions_buffer[0])
            self._ensure_success(
                self._TMR_paramSet(reader, self.TMR_PARAM_REGION_ID, ctypes.byref(region)),
                "TMR_paramSet(/reader/region/id)",
            )

        # Some readers reject explicitly listed ports when checkPort is enabled.
        # Best effort: disable strict port check when supported.
        check_port = ctypes.c_bool(False)
        self._TMR_paramSet(reader, self.TMR_PARAM_ANTENNA_CHECKPORT, ctypes.byref(check_port))

        requested_antennas = [int(a) for a in self.active_ant if int(a) > 0]
        connected_antennas = self._get_uint8_list_param(reader, self.TMR_PARAM_ANTENNA_CONNECTEDPORTLIST)

        attempts: list[list[int]] = []
        if connected_antennas and requested_antennas:
            intersection = [a for a in requested_antennas if a in connected_antennas]
            if intersection:
                attempts.append(intersection)
        if requested_antennas:
            attempts.append(requested_antennas)
        if connected_antennas:
            attempts.append(connected_antennas)
        attempts.append([])

        seen = set()
        last_status = self.TMR_SUCCESS
        selected_plan: list[int] | None = None
        for candidate in attempts:
            key = tuple(candidate)
            if key in seen:
                continue
            seen.add(key)

            status = self._set_read_plan(reader, candidate)
            if status == self.TMR_SUCCESS:
                selected_plan = candidate
                break

            last_status = status
            if self._is_invalid_antenna_status(status):
                logging.warning(
                    "%s - invalid antenna plan %s (%s). Trying fallback.",
                    self.name,
                    candidate if candidate else "AUTO",
                    self._status_to_text(status),
                )
                continue

            self._ensure_success(status, "TMR_paramSet(/reader/read/plan)")

        if selected_plan is None:
            self._ensure_success(last_status, "TMR_paramSet(/reader/read/plan)")

        if selected_plan:
            self.effective_antennas = selected_plan.copy()
            logging.info("%s - read plan antennas: %s", self.name, selected_plan)
        else:
            self.effective_antennas = []
            logging.info("%s - read plan antennas: AUTO", self.name)

        protocol = ctypes.c_int(self.TMR_TAG_PROTOCOL_GEN2)
        self._TMR_paramSet(reader, self.TMR_PARAM_TAGOP_PROTOCOL, ctypes.byref(protocol))

        tag_encoding = ctypes.c_int(self.gen2_tag_encoding)
        status = self._TMR_paramSet(reader, self.TMR_PARAM_GEN2_TAGENCODING, ctypes.byref(tag_encoding))
        if status != self.TMR_SUCCESS:
            logging.warning("%s - Could not set GEN2 tag encoding: %s", self.name, self._status_to_text(status))

        power = self.read_power * 100 if self.read_power <= 100 else self.read_power
        read_power = ctypes.c_int32(power)
        self._TMR_paramSet(reader, self.TMR_PARAM_RADIO_READPOWER, ctypes.byref(read_power))

        session = ctypes.c_int(self.session)
        self._TMR_paramSet(reader, self.TMR_PARAM_GEN2_SESSION, ctypes.byref(session))

        metadata = ctypes.c_uint16(
            self.TMR_TRD_METADATA_FLAG_READCOUNT
            | self.TMR_TRD_METADATA_FLAG_RSSI
            | self.TMR_TRD_METADATA_FLAG_ANTENNAID
            | self.TMR_TRD_METADATA_FLAG_TIMESTAMP
            | self.TMR_TRD_METADATA_FLAG_PROTOCOL
            | self.TMR_TRD_METADATA_FLAG_DATA
        )
        self._TMR_paramSet(reader, self.TMR_PARAM_METADATAFLAG, ctypes.byref(metadata))

    def _open_reader(self, port: str):
        if self._reader is not None:
            return

        reader = ctypes.POINTER(_TMR_Reader)()
        uri = self._reader_uri(port).encode()
        self._ensure_success(
            self._TMR_create_alloc(ctypes.byref(reader), uri),
            f"TMR_create_alloc({uri.decode(errors='ignore')})",
        )
        try:
            self._ensure_success(self._TMR_connect(reader), "TMR_connect")
            self._set_antenna_port_switch_gpos(reader)
            self._configure_beep_gpo(reader)
            self._configure_reader_params(reader)
        except Exception:
            try:
                self._TMR_destroy(reader)
            except Exception:
                pass
            raise

        self._reader = reader
        self._active_port = port
        logging.info("%s connected via Mercury C API on %s", self.name, port)

    def _close_reader(self):
        if self._reader is None:
            return

        if self._beep_is_high:
            try:
                self._beep_set_level(False)
            except Exception:
                pass
            self._beep_is_high = False

        try:
            self._TMR_destroy(self._reader)
        except Exception as exc:
            logging.warning("%s reader close warning: %s", self.name, exc)
        finally:
            self._reader = None
            self._active_port = None

    def _read_tags_once(self) -> list[tuple[str, str | None, int | None, int | None]]:
        if self._reader is None:
            return []

        self._service_beep_state()

        count = ctypes.c_int32(-1)
        status = self._TMR_read(self._reader, ctypes.c_uint32(self._read_timeout_ms), ctypes.byref(count))
        if status != self.TMR_SUCCESS:
            if status in {self.TMR_ERROR_NO_TAGS, self.TMR_ERROR_NO_TAGS_FOUND}:
                return []
            msg = self._status_to_text(status).lower()
            if "no tag" in msg:
                return []
            raise RuntimeError(f"TMR_read failed: {self._status_to_text(status)}")

        tags = []
        while self._TMR_hasMoreTags(self._reader) == self.TMR_SUCCESS:
            trd = _TMR_TagReadData()
            if self._TMR_TRD_init is not None:
                self._TMR_TRD_init(ctypes.byref(trd))

            status = self._TMR_getNextTag(self._reader, ctypes.byref(trd))
            if status != self.TMR_SUCCESS:
                break

            epc_len = int(trd.tag.epcByteCount)
            if epc_len <= 0:
                continue

            epc = bytes(trd.tag.epc[:epc_len]).hex()
            tid = self._extract_tid_from_trd(trd)

            antenna = int(trd.antenna) if trd.antenna > 0 else None
            rssi = int(trd.rssi) if trd.rssi != 0 else None
            tags.append((epc, tid, antenna, rssi))

        if tags:
            self._trigger_beep_non_blocking()
        else:
            self._service_beep_state()

        return tags

    async def connect(self):
        """Connect to reader and keep Mercury inventory loop alive."""
        while self._running:
            try:
                port_to_use = self.port
                if self.is_auto:
                    port_to_use = self._resolve_auto_port()
                    if port_to_use is None:
                        logging.warning("%s - No AUTO port found for VID=%s PID=%s", self.name, self.vid, self.pid)
                        await asyncio.sleep(self.reconnection_time)
                        continue

                await asyncio.to_thread(self._open_reader, port_to_use)
                self.is_connected = True

                if self.start_reading:
                    self.is_reading = True

                while self._running and self.is_connected:
                    if not self.is_reading:
                        await asyncio.sleep(self._idle_sleep)
                        continue

                    rows = await asyncio.to_thread(self._read_tags_once)
                    for epc, tid, ant, rssi in rows:
                        if self.read_rssi > 0 and rssi is not None and rssi < (-abs(self.read_rssi)):
                            continue

                        try:
                            tag = TagSchema(
                                epc=epc,
                                tid=tid,
                                ant=ant,
                                rssi=rssi,
                            ).model_dump()
                            self.emit_event("tag", tag)
                        except Exception as exc:
                            logging.error("Error parsing tag data: %s", exc)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.warning("%s - Mercury connection/read error: %s", self.name, exc)
            finally:
                await asyncio.to_thread(self._close_reader)
                self.is_connected = False
                self.is_reading = False

            if self._running:
                await asyncio.sleep(self.reconnection_time)

    async def disconnect(self):
        self.is_reading = False
        self.is_connected = False
        await asyncio.to_thread(self._close_reader)

    async def close(self):
        """Shut down background tasks and close Mercury resources."""
        self._running = False
        self.is_reading = False
        self.is_connected = False
        await asyncio.to_thread(self._close_reader)
        await self.shutdown()

    async def start_inventory(self):
        if not self.is_connected:
            return False
        self.is_reading = True
        return True

    async def stop_inventory(self):
        if not self.is_connected:
            return False
        self.is_reading = False
        return True

    async def write(self, to_send, verbose=False):
        cmd = str(to_send).strip().lower()
        if cmd in {"readtag on", "read on", "#read:on"}:
            await self.start_inventory()
            return
        if cmd in {"readtag off", "read off", "#read:off"}:
            await self.stop_inventory()
            return

        if verbose:
            logging.warning("%s - raw command ignored in mercury backend: %s", self.name, to_send)
