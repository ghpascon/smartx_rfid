import json
import asyncio
from unittest.mock import Mock, patch

import pytest
from sllurp import llrp

from smartx_rfid.devices.RFID.R420._main import R420
from smartx_rfid.devices.device_manager import DeviceManager
from smartx_rfid.schemas.tag import WriteTagValidator


class TestR420:
    def test_create_object_default(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()

            assert isinstance(device, R420)
            assert device.name == "R420"
            assert device.device_type == "rfid"
            assert device.ip == "192.168.1.100"
            assert device.llrp_port == 5084
            assert device.read_tid is True
            assert device.is_connected is False
            assert device.is_reading is False

    def test_create_object_epc_only(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_tid=False)
            assert device.read_tid is False

    def test_handle_tag_report_epc_tid_default(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_tid=True)
            device.on_event = Mock()

            device.handle_tag_report(
                {
                    "epc": "E20000112233445566778899",
                    "tid": "300833B2DDD901148000000F",
                    "ant": 2,
                    "rssi": -57,
                }
            )

            tag_calls = [c for c in device.on_event.call_args_list if c[0][1] == "tag"]
            assert len(tag_calls) == 1

            payload = tag_calls[0][0][2]
            assert payload["epc"] == "e20000112233445566778899"
            assert payload["tid"] == "300833b2ddd901148000000f"
            assert payload["ant"] == 2
            assert payload["rssi"] == -57

    def test_handle_tag_report_epc_only(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_tid=False)
            device.on_event = Mock()

            device.handle_tag_report(
                {
                    "epc": "E20000112233445566778899",
                    "tid": "300833B2DDD901148000000F",
                    "ant": 1,
                    "rssi": -45,
                }
            )

            tag_calls = [c for c in device.on_event.call_args_list if c[0][1] == "tag"]
            assert len(tag_calls) == 1

            payload = tag_calls[0][0][2]
            assert payload["epc"] == "e20000112233445566778899"
            assert payload["tid"] is None

    def test_handle_tag_report_epc_bytes_from_sllurp(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_tid=False)
            device.on_event = Mock()

            device.handle_tag_report(
                {
                    "EPC": b"e2801191a5030069b5f5956b",
                    "AntennaID": 1,
                    "PeakRSSI": -48,
                }
            )

            tag_calls = [c for c in device.on_event.call_args_list if c[0][1] == "tag"]
            assert len(tag_calls) == 1

            payload = tag_calls[0][0][2]
            assert payload["epc"] == "e2801191a5030069b5f5956b"
            assert payload["ant"] == 1
            assert payload["rssi"] == -48

    @pytest.mark.asyncio
    async def test_start_stop_inventory(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.is_connected = True

            started = await device.start_inventory()
            stopped = await device.stop_inventory()

            assert started is True
            assert stopped is True
            assert device.is_reading is False

    @pytest.mark.asyncio
    async def test_gpi_trigger_blocks_inventory(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(gpi_start=True)
            device.is_connected = True

            started = await device.start_inventory(check_gpi=True)
            assert started is False
            assert device.is_reading is False

    def test_no_gpo_support(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            assert not hasattr(device, "write_gpo")

    def test_refresh_serial_number_ignores_unknown(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.on_event = Mock()

            class FakeLLRP:
                reader_config = {}
                capabilities = {}

            class FakeClient:
                llrp = FakeLLRP()

            device._client = FakeClient()
            device._refresh_serial_number()

            assert device.serial_number is None
            serial_calls = [c for c in device.on_event.call_args_list if c[0][1] == "serial_number"]
            assert serial_calls == []

    def test_refresh_serial_number_emits_once_for_same_value(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.on_event = Mock()

            class FakeLLRP:
                reader_config = {
                    "Identification": {
                        "ReaderID": "001625ffff103019",
                    }
                }
                capabilities = {}

            class FakeClient:
                llrp = FakeLLRP()

            device._client = FakeClient()

            device._refresh_serial_number()
            device._refresh_serial_number()

            assert device.serial_number == "001625ffff103019"
            serial_calls = [c for c in device.on_event.call_args_list if c[0][1] == "serial_number"]
            assert len(serial_calls) == 1

    def test_choose_reader_mode_max_miller_4(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_mode="max_miller_4")
            selected = device._choose_reader_mode(
                [
                    {"ModeIdentifier": 1000, "M": 2, "BDR": 300000},
                    {"ModeIdentifier": 1002, "M": 4, "BDR": 250000},
                    {"ModeIdentifier": 1003, "M": 4, "BDR": 320000},
                ]
            )
            assert selected is not None
            assert selected["ModeIdentifier"] == 1003

    def test_choose_reader_mode_by_identifier(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(mode_identifier=1002)
            selected = device._choose_reader_mode(
                [
                    {"ModeIdentifier": 1000, "M": 2, "BDR": 300000},
                    {"ModeIdentifier": 1002, "M": 4, "BDR": 250000},
                ]
            )
            assert selected is not None
            assert selected["ModeIdentifier"] == 1002

    def test_build_write_target_spec_none(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            validated = WriteTagValidator(
                target_identifier=None,
                target_value=None,
                new_epc="e20000112233445566778899",
                password="00000000",
            )
            assert device._build_write_target_spec(validated) is None

    def test_build_write_target_spec_epc(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            validated = WriteTagValidator(
                target_identifier="epc",
                target_value="e20000112233445566778899",
                new_epc="e200001122334455667788aa",
                password="00000000",
            )
            target = device._build_write_target_spec(validated)
            assert target is not None
            assert target.MB == 1
            assert target.Pointer == 32
            assert target.TagMask == "f" * len("e20000112233445566778899")
            assert target.TagData == "e20000112233445566778899"

    def test_build_write_target_spec_tid(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            validated = WriteTagValidator(
                target_identifier="tid",
                target_value="300833b2ddd901148000000f",
                new_epc="e200001122334455667788aa",
                password="00000000",
            )
            target = device._build_write_target_spec(validated)
            assert target is not None
            assert target.MB == 2
            assert target.Pointer == 0
            assert target.TagMask == "f" * len("300833b2ddd901148000000f")
            assert target.TagData == "300833b2ddd901148000000f"

    @pytest.mark.asyncio
    async def test_write_epc_no_target_uses_llrp_default_target(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.is_connected = True
            device.is_reading = True

            class FakeClient:
                def __init__(self):
                    self.op_spec = None
                    self.target_spec = "unset"

                def start_access_spec(self, op_spec, target_spec=None, stop_after_count=0, access_spec_id=1):
                    self.op_spec = op_spec
                    self.target_spec = target_spec

            fake = FakeClient()
            device._client = fake

            task = asyncio.create_task(
                device.write_epc(
                    target_identifier=None,
                    target_value=None,
                    new_epc="e200001122334455667788aa",
                    password="00000000",
                )
            )

            await asyncio.sleep(0)
            assert fake.op_spec is not None
            assert fake.target_spec is None

            device._resolve_pending_write_results(
                {
                    "C1G2WriteOpSpecResult": {
                        "Result": 0,
                        "OpSpecID": fake.op_spec.OpSpecID,
                        "NumWordsWritten": fake.op_spec.WriteDataWordCount,
                    }
                }
            )

            ok = await task
            assert ok is True

    @pytest.mark.asyncio
    async def test_write_epc_success(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.is_connected = True
            device.is_reading = True

            class FakeClient:
                def __init__(self):
                    self.op_spec = None
                    self.target_spec = None

                def start_access_spec(self, op_spec, target_spec=None, stop_after_count=0, access_spec_id=1):
                    self.op_spec = op_spec
                    self.target_spec = target_spec

            fake = FakeClient()
            device._client = fake

            task = asyncio.create_task(
                device.write_epc(
                    target_identifier="epc",
                    target_value="e20000112233445566778899",
                    new_epc="e200001122334455667788aa",
                    password="00000000",
                )
            )

            await asyncio.sleep(0)
            assert fake.op_spec is not None
            assert fake.target_spec is not None

            device._resolve_pending_write_results(
                {
                    "C1G2WriteOpSpecResult": {
                        "Result": 0,
                        "OpSpecID": fake.op_spec.OpSpecID,
                        "NumWordsWritten": fake.op_spec.WriteDataWordCount,
                    }
                }
            )

            ok = await task
            assert ok is True

    @pytest.mark.asyncio
    async def test_resolve_write_result_with_access_spec_fallback(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()

            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            device._pending_write_results[2001] = fut
            device._pending_write_results_by_access_spec[3001] = fut

            # Some readers may include AccessSpecID consistently while OpSpecID can mismatch.
            device._resolve_pending_write_results(
                {
                    "AccessSpecID": 3001,
                    "C1G2WriteOpSpecResult": {
                        "Result": 0,
                        "OpSpecID": 9999,
                        "NumWordsWritten": 6,
                    },
                }
            )

            assert fut.done()
            success, message, result = fut.result()
            assert success is True
            assert "Write succeeded" in message
            assert result["NumWordsWritten"] == 6

    @pytest.mark.asyncio
    async def test_resolve_write_result_with_access_spec_only_when_opspec_invalid(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()

            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            device._pending_write_results[2002] = fut
            device._pending_write_results_by_access_spec[3002] = fut

            # Some readers may provide AccessSpecID but malformed OpSpecID.
            device._resolve_pending_write_results(
                {
                    "AccessSpecID": 3002,
                    "C1G2WriteOpSpecResult": {
                        "Result": 0,
                        "OpSpecID": "invalid",
                        "NumWordsWritten": 6,
                    },
                }
            )

            assert fut.done()
            success, message, result = fut.result()
            assert success is True
            assert "Write succeeded" in message
            assert result["NumWordsWritten"] == 6

    @pytest.mark.asyncio
    async def test_write_epc_pauses_and_restores_tid_access_spec(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420(read_tid=True)
            device.is_connected = True
            device.is_reading = True
            device._tid_access_started = True

            class FakeLLRP:
                state = llrp.LLRPReaderState.STATE_INVENTORYING

                def __init__(self):
                    self.deleted = []

                def send_DELETE_ACCESSSPEC(self, access_spec_id):
                    self.deleted.append(access_spec_id)

            class FakeClient:
                def __init__(self):
                    self.llrp = FakeLLRP()
                    self.op_spec = None

                def start_access_spec(self, op_spec, target_spec=None, stop_after_count=0, access_spec_id=1):
                    self.op_spec = op_spec

            fake = FakeClient()
            device._client = fake

            task = asyncio.create_task(
                device.write_epc(
                    target_identifier="epc",
                    target_value="e20000112233445566778899",
                    new_epc="e200001122334455667788aa",
                    password="00000000",
                )
            )

            await asyncio.sleep(0)
            assert fake.op_spec is not None

            device._resolve_pending_write_results(
                {
                    "C1G2WriteOpSpecResult": {
                        "Result": 0,
                        "OpSpecID": fake.op_spec.OpSpecID,
                        "NumWordsWritten": fake.op_spec.WriteDataWordCount,
                    }
                }
            )

            ok = await task
            assert ok is True
            assert device._tid_access_started is True
            assert device._tid_access_spec_id in fake.llrp.deleted

    def test_cleanup_access_spec_skips_when_disconnecting(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.is_connected = True
            device._stop_connection = True

            class FakeLLRP:
                state = llrp.LLRPReaderState.STATE_INVENTORYING

                def __init__(self):
                    self.deleted = []

                def send_DELETE_ACCESSSPEC(self, access_spec_id):
                    self.deleted.append(access_spec_id)

            class FakeClient:
                def __init__(self):
                    self.llrp = FakeLLRP()

            fake = FakeClient()
            device._cleanup_access_spec(fake, 1234)
            assert fake.llrp.deleted == []

    def test_cleanup_access_spec_deletes_in_allowed_state(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            device = R420()
            device.is_connected = True
            device._stop_connection = False

            class FakeLLRP:
                state = llrp.LLRPReaderState.STATE_INVENTORYING

                def __init__(self):
                    self.deleted = []

                def send_DELETE_ACCESSSPEC(self, access_spec_id):
                    self.deleted.append(access_spec_id)

            class FakeClient:
                def __init__(self):
                    self.llrp = FakeLLRP()

            fake = FakeClient()
            device._cleanup_access_spec(fake, 1234)
            assert fake.llrp.deleted == [1234]


@pytest.mark.asyncio
async def test_device_manager_loads_r420(tmp_path):
    cfg = {
        "READER": "R420",
        "IP": "127.0.0.1",
        "START_READING": False,
        "READ_TID": True,
    }
    (tmp_path / "reader_r420.json").write_text(json.dumps(cfg), encoding="utf-8")

    manager = DeviceManager(devices_path=str(tmp_path))
    await manager._load_devices_async()

    device = manager.get_device("reader_r420")
    assert device is not None
    assert isinstance(device, R420)
