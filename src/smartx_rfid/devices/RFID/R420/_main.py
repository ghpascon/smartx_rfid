import asyncio
import logging
import time
from typing import Any, Optional

from smartx_rfid.devices._base import DeviceBase
from smartx_rfid.schemas import TagSchema
from smartx_rfid.schemas.tag import WriteTagValidator
from smartx_rfid.utils import regex_hex
from sllurp import llrp


class R420(DeviceBase):
    """Impinj R420 RFID reader using sllurp (LLRP).

    Notes:
    - Connection is asynchronous and auto-reconnects.
    - Tag reports are emitted as `tag` events following TagSchema.
    - `read_tid=True` (default) emits EPC+TID when available.
    - `read_tid=False` emits EPC only.
    """

    def __init__(
        self,
        name: str = "R420",
        ip: str = "192.168.1.100",
        llrp_port: int = 5084,
        reconnection_time: int = 3,
        connect_timeout: float = 5.0,
        socket_read_timeout: float = 2.0,
        keepalive_interval: float = 10.0,
        start_reading: bool = True,
        gpi_start: bool = False,
        read_tid: bool = True,
        session: int = 1,
        active_ant: list[int] | None = None,
        read_power: int = 30,
        read_rssi: int = -80,
        emit_raw_llrp: bool = False,
        tid_word_count: int = 6,
        read_mode: str = "max_miller_4",
        mode_identifier: int | None = None,
        **kwargs,
    ):
        DeviceBase.__init__(self)

        self.name = name if isinstance(name, str) and name else "R420"
        self.device_type = "rfid"

        self.ip = ip if isinstance(ip, str) and ip.strip() else "192.168.1.100"

        if not isinstance(llrp_port, int) or not (1 <= llrp_port <= 65535):
            llrp_port = 5084
        self.llrp_port = llrp_port

        if not isinstance(reconnection_time, int) or reconnection_time < 1:
            reconnection_time = 3
        self.reconnection_time = reconnection_time

        self.connect_timeout = self._coerce_float(connect_timeout, 5.0, min_value=0.1)
        self.socket_read_timeout = self._coerce_float(socket_read_timeout, 2.0, min_value=0.2)
        self.keepalive_interval = self._coerce_float(keepalive_interval, 10.0, min_value=1.0)

        self.start_reading = bool(start_reading)
        self.is_gpi_trigger_on = bool(gpi_start)
        if self.is_gpi_trigger_on:
            self.start_reading = False

        self.read_tid = bool(read_tid)

        if session not in (0, 1, 2, 3):
            session = 1
        self.session = session

        self.active_ant = self._normalize_antennas(active_ant)

        if not isinstance(read_power, int):
            read_power = 30
        if read_power < 10 or read_power > 33:
            read_power = 30
        self.read_power = read_power

        if not isinstance(read_rssi, int):
            read_rssi = -80
        if read_rssi < -120 or read_rssi > 0:
            read_rssi = -80
        self.read_rssi = read_rssi

        self.emit_raw_llrp = bool(emit_raw_llrp)

        self.read_mode = self._normalize_read_mode(read_mode)
        self.mode_identifier = mode_identifier if isinstance(mode_identifier, int) and mode_identifier > 0 else None
        self._applied_mode_identifier: int | None = None

        if not isinstance(tid_word_count, int) or tid_word_count <= 0:
            tid_word_count = 6
        self.tid_word_count = tid_word_count

        self.serial_number = None
        self.is_connected = False
        self.is_reading = False

        self._stop_connection = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._disconnect_event: Optional[asyncio.Event] = None
        self._client: Optional[llrp.LLRPReaderClient] = None
        self._connect_lock = asyncio.Lock()
        self._inventory_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._tid_access_started = False

        self._tid_access_spec_id = 100
        self._tid_op_spec_id = 100
        self._next_write_spec_id = 1000
        self._pending_write_results: dict[int, asyncio.Future] = {}
        self._pending_write_results_by_access_spec: dict[int, asyncio.Future] = {}

    @staticmethod
    def _normalize_read_mode(value: Any) -> str:
        if not isinstance(value, str):
            return "max_miller_4"
        normalized = value.strip().lower()
        if normalized in {"auto", "max_miller_4"}:
            return normalized
        return "max_miller_4"

    @staticmethod
    def _coerce_float(value: Any, default: float, min_value: float) -> float:
        try:
            v = float(value)
        except Exception:
            return default
        if v < min_value:
            return default
        return v

    @staticmethod
    def _normalize_antennas(active_ant: list[int] | None) -> list[int]:
        if not isinstance(active_ant, list) or not active_ant:
            return [1]
        out: list[int] = []
        for ant in active_ant:
            try:
                ant_int = int(ant)
            except Exception:
                continue
            if 1 <= ant_int <= 4 and ant_int not in out:
                out.append(ant_int)
        return out or [1]

    @staticmethod
    def _normalize_hex_frame(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        txt = value.strip().replace(" ", "")
        if txt == "" or len(txt) % 2 != 0:
            return None
        if not regex_hex(txt):
            return None
        return txt.lower()

    @staticmethod
    def _clean_hex(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
            # sllurp may already return ASCII-hex bytes (e.g. b"e280...").
            try:
                as_text = raw.decode("ascii").strip().lower().replace(" ", "")
                if as_text and regex_hex(as_text):
                    return as_text
            except Exception:
                pass
            # Fallback for binary payloads.
            return raw.hex().lower()
        text = str(value).strip().lower().replace(" ", "")
        return "".join(ch for ch in text if ch in "0123456789abcdef")

    @staticmethod
    def _coerce_reader_text(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
            try:
                text = raw.decode("ascii").strip()
            except Exception:
                text = raw.hex()
        else:
            text = str(value).strip()

        if text == "":
            return None

        lower = text.lower()
        if lower in {"none", "null", "unknown"}:
            return None

        return text

    def _extract_reader_serial(self, client: llrp.LLRPReaderClient | None) -> str | None:
        if client is None:
            return None

        llrp_client = getattr(client, "llrp", None)
        if llrp_client is None:
            return None

        candidates: list[Any] = []

        reader_config = getattr(llrp_client, "reader_config", None)
        if isinstance(reader_config, dict):
            identification = reader_config.get("Identification")
            if isinstance(identification, dict):
                candidates.append(identification.get("ReaderID"))

        #     detailed = reader_config.get("ImpinjDetailedVersion")
        #     if isinstance(detailed, dict):
        #         candidates.append(detailed.get("SerialNumber"))

        # capabilities = getattr(llrp_client, "capabilities", None)
        # if isinstance(capabilities, dict):
        #     detailed = capabilities.get("ImpinjDetailedVersion")
        #     if isinstance(detailed, dict):
        #         candidates.append(detailed.get("SerialNumber"))

        for value in candidates:
            parsed = self._coerce_reader_text(value)
            if parsed:
                return parsed

        return None

    def _refresh_serial_number(self) -> None:
        serial = self._extract_reader_serial(self._client)
        if serial is None:
            # Avoid emitting fallback identifiers repeatedly while reader metadata
            # is still being populated by LLRP capabilities/config responses.
            return

        if self.serial_number == serial:
            return

        self.serial_number = serial
        self.emit_event("serial_number", self.serial_number)

    async def connect(self):
        """Connect to R420 using sllurp and keep reconnection loop alive."""
        if self._connect_lock.locked():
            logging.info(f"{self.name} - connect() already running")
            return

        async with self._connect_lock:
            self._running = True
            self._stop_connection = False
            self._loop = asyncio.get_running_loop()

            while self._running and not self._stop_connection:
                try:
                    await self._connect_once_sllurp()
                    await self._wait_until_disconnected()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logging.warning(f"{self.name} - connection error: {e}")
                finally:
                    await self._disconnect_client()
                    self.is_reading = False
                    self.is_connected = False
                    self.serial_number = None

                if self._stop_connection or not self._running:
                    break

                await asyncio.sleep(self.reconnection_time)

    def _build_sllurp_config(self) -> llrp.LLRPReaderConfig:
        tag_content_selector = {
            "EnableROSpecID": False,
            "EnableSpecIndex": False,
            "EnableInventoryParameterSpecID": False,
            "EnableAntennaID": True,
            "EnableChannelIndex": False,
            "EnablePeakRSSI": True,
            "EnableFirstSeenTimestamp": False,
            "EnableLastSeenTimestamp": False,
            "EnableTagSeenCount": True,
            "EnableAccessSpecID": True,
        }

        config_dict = {
            "antennas": self.active_ant,
            "session": self.session,
            "start_inventory": bool(self.start_reading and not self.is_gpi_trigger_on),
            "reconnect": False,
            "keepalive_interval": int(self.keepalive_interval * 1000),
            "tag_content_selector": tag_content_selector,
            "tx_power_dbm": float(self.read_power),
            "impinj_extended_configuration": bool(self.read_tid),
        }

        if self.mode_identifier is not None:
            config_dict["mode_identifier"] = int(self.mode_identifier)

        return llrp.LLRPReaderConfig(config_dict)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _choose_reader_mode(self, mode_entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not mode_entries:
            return None

        if self.mode_identifier is not None:
            for mode in mode_entries:
                if self._safe_int(mode.get("ModeIdentifier"), -1) == self.mode_identifier:
                    return mode
            return None

        if self.read_mode == "auto":
            return None

        if self.read_mode == "max_miller_4":
            m4_modes = [mode for mode in mode_entries if self._safe_int(mode.get("M"), -1) == 4]
            if not m4_modes:
                return None
            # Prefer highest backscatter data rate for Miller-4 modes.
            return max(
                m4_modes,
                key=lambda mode: (
                    self._safe_int(mode.get("BDR"), 0),
                    self._safe_int(mode.get("ModeIdentifier"), 0),
                ),
            )

        return None

    def _apply_read_mode_if_possible(self, reader: llrp.LLRPReaderClient) -> None:
        llrp_client = getattr(reader, "llrp", None)
        if llrp_client is None:
            return

        capabilities = getattr(llrp_client, "capabilities", None)
        if not isinstance(capabilities, dict):
            return

        reg_cap = capabilities.get("RegulatoryCapabilities")
        if not isinstance(reg_cap, dict):
            return

        uhf_band = reg_cap.get("UHFBandCapabilities")
        if not isinstance(uhf_band, dict):
            return

        mode_table = uhf_band.get("UHFC1G2RFModeTable")
        if not isinstance(mode_table, dict):
            return

        mode_entries = mode_table.get("UHFC1G2RFModeTableEntry")
        if not isinstance(mode_entries, list):
            return

        selected_mode = self._choose_reader_mode(mode_entries)
        if selected_mode is None:
            if self.mode_identifier is not None:
                logging.warning(
                    f"{self.name} - requested mode_identifier={self.mode_identifier} was not found in reader capabilities"
                )
            return

        selected_mode_id = self._safe_int(selected_mode.get("ModeIdentifier"), -1)
        if selected_mode_id < 0:
            return

        current_mode = getattr(llrp_client, "reader_mode", None)
        current_mode_id = None
        if isinstance(current_mode, dict):
            current_mode_id = self._safe_int(current_mode.get("ModeIdentifier"), -1)

        if current_mode_id == selected_mode_id and self._applied_mode_identifier == selected_mode_id:
            return

        llrp_client.reader_mode = selected_mode
        self._applied_mode_identifier = selected_mode_id
        logging.info(
            f"{self.name} - using read_mode={self.read_mode} (ModeIdentifier={selected_mode_id}, M={selected_mode.get('M')}, BDR={selected_mode.get('BDR')})"
        )

    async def _connect_once_sllurp(self) -> None:
        logging.info(f"{self.name} - connecting to {self.ip}:{self.llrp_port} (sllurp)")
        config = self._build_sllurp_config()
        client = llrp.LLRPReaderClient(self.ip, port=self.llrp_port, config=config, timeout=self.connect_timeout)

        client.add_tag_report_callback(self._on_sllurp_tag_report)
        client.add_disconnected_callback(self._on_sllurp_disconnected)
        client.add_state_callback(llrp.LLRPReaderState.STATE_CONNECTED, self._on_sllurp_state_changed)
        client.add_state_callback(llrp.LLRPReaderState.STATE_SENT_SET_CONFIG, self._on_sllurp_state_changed)
        client.add_state_callback(llrp.LLRPReaderState.STATE_INVENTORYING, self._on_sllurp_state_changed)
        client.add_state_callback(llrp.LLRPReaderState.STATE_PAUSED, self._on_sllurp_state_changed)
        client.add_state_callback(llrp.LLRPReaderState.STATE_DISCONNECTED, self._on_sllurp_state_changed)

        self._disconnect_event = asyncio.Event()
        self._tid_access_started = False
        self._client = client

        await asyncio.to_thread(client.connect, True)

        self.is_connected = True
        self._refresh_serial_number()

    async def _wait_until_disconnected(self) -> None:
        while self._running and not self._stop_connection:
            if self._disconnect_event is not None and self._disconnect_event.is_set():
                return
            client = self._client
            if client is None or not client.is_alive():
                return
            await asyncio.sleep(0.2)

    async def _disconnect_client(self) -> None:
        client, self._client = self._client, None
        self._tid_access_started = False

        if client is None:
            return

        try:
            await asyncio.to_thread(client.disconnect, 1.0)
        except Exception:
            pass

        try:
            await asyncio.to_thread(client.join, 1.0)
        except Exception:
            pass

    def _call_soon_threadsafe(self, func, *args) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(func, *args)
            return
        func(*args)

    def _on_sllurp_disconnected(self, _reader) -> None:
        self._call_soon_threadsafe(self._handle_disconnected_callback)

    def _handle_disconnected_callback(self) -> None:
        pending_futures = set(self._pending_write_results.values()) | set(
            self._pending_write_results_by_access_spec.values()
        )
        self._pending_write_results.clear()
        self._pending_write_results_by_access_spec.clear()
        for pending in pending_futures:
            if pending.done():
                continue
            pending.set_exception(ConnectionError(f"{self.name} - disconnected while waiting write result"))

        self.is_reading = False
        self.is_connected = False
        self.serial_number = None
        if self._disconnect_event is not None and not self._disconnect_event.is_set():
            self._disconnect_event.set()

    def _on_sllurp_state_changed(self, reader, newstate) -> None:
        if newstate == llrp.LLRPReaderState.STATE_SENT_SET_CONFIG:
            self._apply_read_mode_if_possible(reader)
        if newstate == llrp.LLRPReaderState.STATE_INVENTORYING and self.read_tid:
            self._ensure_tid_access_spec(reader)
        self._call_soon_threadsafe(self._handle_state_changed, newstate)

    def _handle_state_changed(self, newstate) -> None:
        if newstate == llrp.LLRPReaderState.STATE_CONNECTED:
            self.is_connected = True
            self.is_reading = False
            self._refresh_serial_number()
            return
        if newstate == llrp.LLRPReaderState.STATE_INVENTORYING:
            self.is_connected = True
            self.is_reading = True
            self._refresh_serial_number()
            return
        if newstate == llrp.LLRPReaderState.STATE_PAUSED:
            self.is_connected = True
            self.is_reading = False
            self._refresh_serial_number()
            return
        if newstate == llrp.LLRPReaderState.STATE_DISCONNECTED:
            self._handle_disconnected_callback()

    def _on_sllurp_tag_report(self, _reader, tag_reports) -> None:
        if not isinstance(tag_reports, list):
            return
        self._call_soon_threadsafe(self._handle_tag_batch, tag_reports)

    def _handle_tag_batch(self, tag_reports: list[dict[str, Any]]) -> None:
        for report in tag_reports:
            self._resolve_pending_write_results(report)
            if not self.is_reading:
                continue
            self.handle_tag_report(report)

    def _ensure_tid_access_spec(self, reader: llrp.LLRPReaderClient) -> None:
        if not self.read_tid or self._tid_access_started:
            return
        try:
            op_spec = llrp.C1G2Read(
                OpSpecID=self._tid_op_spec_id,
                AccessPassword=0,
                MB=2,  # TID memory bank
                WordPtr=0,
                WordCount=self.tid_word_count,
            )
            reader.start_access_spec(
                op_spec=op_spec,
                stop_after_count=0,
                access_spec_id=self._tid_access_spec_id,
            )
            self._tid_access_started = True
        except Exception as e:
            logging.warning(f"{self.name} - failed to start TID access spec: {e}")

    def _pause_tid_access_spec_for_write(self, client: llrp.LLRPReaderClient) -> bool:
        if not self.read_tid or not self._tid_access_started:
            return False

        llrp_client = getattr(client, "llrp", None)
        if llrp_client is None:
            return False

        state = getattr(llrp_client, "state", None)
        allowed_states = {
            llrp.LLRPReaderState.STATE_CONNECTED,
            llrp.LLRPReaderState.STATE_INVENTORYING,
            llrp.LLRPReaderState.STATE_PAUSED,
        }
        if state not in allowed_states:
            return False

        try:
            llrp_client.send_DELETE_ACCESSSPEC(self._tid_access_spec_id)
            self._tid_access_started = False
            return True
        except Exception as e:
            logging.debug(f"{self.name} - failed to pause TID access spec before write: {e}")
            return False

    def _extract_tid_from_tag_report(self, report: dict[str, Any]) -> str | None:
        # Impinj extension (preferred)
        impinj_tid = report.get("ImpinjSerializedTID")
        if isinstance(impinj_tid, dict):
            tid = self._clean_hex(impinj_tid.get("TID"))
            if tid:
                return tid

        # AccessSpec read result
        op_result = report.get("C1G2ReadOpSpecResult")
        if isinstance(op_result, dict):
            tid = self._clean_hex(op_result.get("ReadData"))
            if tid:
                return tid
        if isinstance(op_result, list):
            for item in op_result:
                if not isinstance(item, dict):
                    continue
                tid = self._clean_hex(item.get("ReadData"))
                if tid:
                    return tid

        # Compatibility with generic/non-sllurp report payloads
        tid = self._clean_hex(report.get("tid") or report.get("tidHex") or report.get("tid_hex"))
        if tid:
            return tid
        return None

    def _next_write_ids(self) -> tuple[int, int]:
        current = self._next_write_spec_id
        self._next_write_spec_id += 1
        if self._next_write_spec_id > 60000:
            self._next_write_spec_id = 1000
        # Keep OpSpecID and AccessSpecID aligned for easier troubleshooting.
        return current, current

    def _build_write_target_spec(self, validated: WriteTagValidator):
        identifier = validated.target_identifier
        if identifier is None:
            return None

        if validated.target_value is None:
            raise ValueError("target_value is required when target_identifier is provided")

        # In C1G2TargetTag, TagMask selects which bits are compared and TagData is
        # the expected value for those bits. For exact match, mask must be all 1s.
        exact_match_mask = "f" * len(validated.target_value)

        if identifier == "epc":
            # EPC bank: bit pointer 32 skips CRC (16) + PC (16).
            return llrp.C1G2TargetTag(
                MB=1,
                Pointer=32,
                TagMask=exact_match_mask,
                TagData=validated.target_value,
            )

        if identifier == "tid":
            # TID bank starts at bit 0.
            return llrp.C1G2TargetTag(
                MB=2,
                Pointer=0,
                TagMask=exact_match_mask,
                TagData=validated.target_value,
            )

        raise ValueError(f"Unsupported target_identifier: {identifier}")

    def _pop_pending_write_result(
        self, op_spec_id: int | None = None, access_spec_id: int | None = None
    ) -> asyncio.Future | None:
        future = None
        if op_spec_id is not None:
            future = self._pending_write_results.pop(op_spec_id, None)
        if future is None and access_spec_id is not None:
            future = self._pending_write_results_by_access_spec.pop(access_spec_id, None)
        if future is None:
            return None

        for key, value in list(self._pending_write_results.items()):
            if value is future:
                self._pending_write_results.pop(key, None)
                break

        for key, value in list(self._pending_write_results_by_access_spec.items()):
            if value is future:
                self._pending_write_results_by_access_spec.pop(key, None)
                break

        return future

    def _cleanup_access_spec(self, client: llrp.LLRPReaderClient, access_spec_id: int) -> None:
        llrp_client = getattr(client, "llrp", None)
        if llrp_client is None:
            return

        # Avoid sending extra AccessSpec commands while the reader is disconnecting,
        # because this races with stopPolitely() and may trigger reader-side 409 errors.
        if self._stop_connection or not self.is_connected:
            return

        state = getattr(llrp_client, "state", None)
        allowed_states = {
            llrp.LLRPReaderState.STATE_CONNECTED,
            llrp.LLRPReaderState.STATE_INVENTORYING,
            llrp.LLRPReaderState.STATE_PAUSED,
        }
        if state not in allowed_states:
            return

        # Delete directly: stop_after_count=1 already ends the operation,
        # so sending DISABLE+DELETE increases race chances without benefit.
        try:
            llrp_client.send_DELETE_ACCESSSPEC(access_spec_id)
        except Exception:
            pass

    def _resolve_pending_write_results(self, report: dict[str, Any]) -> None:
        report_access_spec_id: int | None = None
        try:
            if report.get("AccessSpecID") is not None:
                report_access_spec_id = int(report.get("AccessSpecID"))
        except Exception:
            report_access_spec_id = None

        results: list[dict[str, Any]] = []

        maybe_write = report.get("C1G2WriteOpSpecResult")
        if isinstance(maybe_write, dict):
            results.append(maybe_write)
        elif isinstance(maybe_write, list):
            results.extend([r for r in maybe_write if isinstance(r, dict)])

        maybe_block_write = report.get("C1G2BlockWriteOpSpecResult")
        if isinstance(maybe_block_write, dict):
            results.append(maybe_block_write)
        elif isinstance(maybe_block_write, list):
            results.extend([r for r in maybe_block_write if isinstance(r, dict)])

        for result in results:
            raw_op_spec_id = result.get("OpSpecID")
            op_spec_id: int | None = None
            try:
                if raw_op_spec_id is not None:
                    op_spec_id = int(raw_op_spec_id)
            except Exception:
                op_spec_id = None

            future = self._pop_pending_write_result(op_spec_id=op_spec_id, access_spec_id=report_access_spec_id)
            if future is None or future.done():
                continue

            try:
                status = int(result.get("Result"))
            except Exception:
                status = -1

            words_written = result.get("NumWordsWritten")
            success = status == 0
            op_spec_label = op_spec_id if op_spec_id is not None else raw_op_spec_id
            if success:
                msg = f"Write succeeded (OpSpecID={op_spec_label}, words={words_written})"
            else:
                msg = f"Write failed (OpSpecID={op_spec_label}, Result={status}, words={words_written})"

            future.set_result((success, msg, result))

    def _normalize_tag_report(self, report: dict[str, Any]) -> dict[str, Any] | None:
        epc = self._clean_hex(
            report.get("EPC") or report.get("EPC-96") or report.get("epc") or report.get("EPC") or report.get("epcHex")
        )
        if epc == "" or len(epc) % 4 != 0:
            return None

        tid: str | None = None
        if self.read_tid:
            tid_raw = self._extract_tid_from_tag_report(report)
            if tid_raw:
                if len(tid_raw) >= 24:
                    tid = tid_raw[:24]
                else:
                    tid = tid_raw.zfill(24)

        ant = report.get("AntennaID")
        if ant is None:
            ant = report.get("ant")
        try:
            ant = int(ant) if ant is not None else None
        except Exception:
            ant = None

        rssi = report.get("PeakRSSI")
        if rssi is None:
            rssi = report.get("rssi")

        if rssi is not None:
            try:
                rssi = int(rssi)
            except Exception:
                rssi = None

        try:
            validated = TagSchema(
                epc=epc,
                tid=tid,
                ant=ant,
                rssi=rssi,
                protected=False,
            )
        except Exception as e:
            logging.debug(f"{self.name} - invalid tag report dropped: {e}")
            return None

        return validated.model_dump()

    def handle_tag_report(self, report: dict[str, Any]) -> None:
        """Public entrypoint for parsed reports from adapters/callbacks."""
        normalized = self._normalize_tag_report(report)
        if not isinstance(normalized, dict) or not normalized.get("epc"):
            return
        if self.read_tid and not normalized.get("tid"):
            return

        self.emit_event("tag", normalized)

    async def on_tag_report(self, report: dict[str, Any]) -> None:
        """Async wrapper for compatibility with async callback pipelines."""
        self.handle_tag_report(report)

    async def start_inventory(self, check_gpi: bool = True) -> bool:
        if not self.is_connected:
            logging.warning(f"{self.name} - cannot start inventory: not connected")
            return False
        if check_gpi and self.is_gpi_trigger_on:
            logging.info(f"{self.name} - cannot start inventory: GPI trigger is on")
            return False

        async with self._inventory_lock:
            if self.is_reading:
                return True

            # Compatibility fallback for mocked scenarios/tests
            client = self._client
            if client is None:
                self.is_reading = True
                return True

            try:
                reader_llrp = client.llrp
                state = reader_llrp.state
                if state == llrp.LLRPReaderState.STATE_PAUSED:
                    reader_llrp.resume()
                elif state != llrp.LLRPReaderState.STATE_INVENTORYING:
                    reader_llrp.startInventory(force_regen_rospec=False)
                self.is_reading = True
                return True
            except Exception as e:
                logging.error(f"{self.name} - error starting inventory: {e}")
                return False

    async def stop_inventory(self, check_gpi: bool = True) -> bool:
        if not self.is_connected:
            logging.warning(f"{self.name} - cannot stop inventory: not connected")
            return False
        if check_gpi and self.is_gpi_trigger_on:
            logging.info(f"{self.name} - cannot stop inventory: GPI trigger is on")
            return False

        async with self._inventory_lock:
            if not self.is_reading:
                return True

            # Compatibility fallback for mocked scenarios/tests
            client = self._client
            if client is None:
                self.is_reading = False
                return True

            try:
                reader_llrp = client.llrp
                if reader_llrp.state == llrp.LLRPReaderState.STATE_INVENTORYING:
                    reader_llrp.pause(force=True)
                self.is_reading = False
                return True
            except Exception as e:
                logging.error(f"{self.name} - error stopping inventory: {e}")
                return False

    async def write(self, to_send: bytes | str, verbose: bool = True) -> None:
        client = self._client
        if client is None:
            raise ConnectionError("R420 sllurp client is not connected")

        if isinstance(to_send, bytes):
            payload = to_send
        elif isinstance(to_send, str):
            txt = to_send.strip()
            if txt and len(txt) % 2 == 0 and regex_hex(txt):
                payload = bytes.fromhex(txt)
            else:
                payload = txt.encode("utf-8")
        else:
            payload = str(to_send).encode("utf-8")

        await asyncio.to_thread(client.send_data, payload)

        if verbose:
            logging.info(f"{self.name} - sent {len(payload)} bytes")

    async def disconnect(self):
        self._stop_connection = True

        try:
            if self.is_connected and self.is_reading:
                await self.stop_inventory(check_gpi=False)
        except Exception:
            pass

        await self._disconnect_client()
        self.is_reading = False
        self.is_connected = False
        self.serial_number = None

    async def close(self):
        self._running = False
        self._stop_connection = True
        try:
            await self.disconnect()
        except Exception:
            pass
        await self.shutdown()

    async def write_epc(self, target_identifier: str | None, target_value: str | None, new_epc: str, password: str):
        validated = WriteTagValidator(
            target_identifier=target_identifier,
            target_value=target_value,
            new_epc=new_epc,
            password=password,
        )

        logging.info(
            f"{self.name} - Writing EPC: {validated.new_epc} on target ({validated.target_identifier}){validated.target_value}"
        )

        if not self.is_connected or self._client is None:
            raise RuntimeError(f"{self.name} - cannot write EPC: reader is not connected")

        async with self._write_lock:
            client = self._client
            if client is None:
                raise RuntimeError(f"{self.name} - cannot write EPC: reader client is unavailable")

            def _reader_is_inventorying() -> bool:
                reader_llrp = getattr(client, "llrp", None)
                if reader_llrp is None:
                    return bool(self.is_reading)
                return getattr(reader_llrp, "state", None) == llrp.LLRPReaderState.STATE_INVENTORYING

            async def _wait_inventorying(timeout: float = 3.0) -> bool:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if _reader_is_inventorying():
                        return True
                    await asyncio.sleep(0.05)
                return _reader_is_inventorying()

            was_inventorying = _reader_is_inventorying()
            started_by_write = False
            if not was_inventorying:
                ok = await self.start_inventory(check_gpi=False)
                if not ok:
                    raise RuntimeError(f"{self.name} - cannot write EPC: failed to start inventory")
                started_by_write = True
                inventory_ready = await _wait_inventorying(timeout=3.0)
                if not inventory_ready:
                    raise RuntimeError(
                        f"{self.name} - cannot write EPC: inventory did not enter STATE_INVENTORYING in time"
                    )

            op_spec_id, access_spec_id = self._next_write_ids()
            target_spec = self._build_write_target_spec(validated)
            tid_access_was_paused = self._pause_tid_access_spec_for_write(client)

            write_bytes = bytes.fromhex(validated.new_epc)
            write_word_count = len(write_bytes) // 2
            access_password = int(validated.password, 16)

            op_spec = llrp.C1G2Write(
                OpSpecID=op_spec_id,
                AccessPassword=access_password,
                MB=1,
                WordPtr=2,
                WriteDataWordCount=write_word_count,
                WriteData=write_bytes,
            )

            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            self._pending_write_results[op_spec_id] = future
            self._pending_write_results_by_access_spec[access_spec_id] = future

            try:
                client.start_access_spec(
                    op_spec=op_spec,
                    target_spec=target_spec,
                    stop_after_count=1,
                    access_spec_id=access_spec_id,
                )
            except Exception as e:
                self._pop_pending_write_result(op_spec_id=op_spec_id, access_spec_id=access_spec_id)
                raise RuntimeError(f"{self.name} - failed to submit write access spec: {e}") from e

            try:
                success, message, _ = await asyncio.wait_for(future, timeout=5.0)
            except ConnectionError as e:
                self._pop_pending_write_result(op_spec_id=op_spec_id, access_spec_id=access_spec_id)
                raise RuntimeError(f"{self.name} - write aborted: {e}") from e
            except asyncio.TimeoutError as e:
                self._pop_pending_write_result(op_spec_id=op_spec_id, access_spec_id=access_spec_id)
                raise RuntimeError(
                    f"{self.name} - timeout waiting write result (OpSpecID={op_spec_id}, AccessSpecID={access_spec_id}). "
                    "No matching tag/report was received in time."
                ) from e
            finally:
                self._cleanup_access_spec(client, access_spec_id)
                if tid_access_was_paused and self.is_connected:
                    self._ensure_tid_access_spec(client)
                if started_by_write:
                    await self.stop_inventory(check_gpi=False)

            if not success:
                raise RuntimeError(f"{self.name} - EPC write failed: {message}")

            return True
