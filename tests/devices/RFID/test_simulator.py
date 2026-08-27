import asyncio
import pytest
from unittest.mock import Mock, patch

from smartx_rfid.devices.RFID.SIMULATOR._main import SIMULATOR


class TestSimulator:
    def test_create_object_default(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            sim = SIMULATOR()
            assert isinstance(sim, SIMULATOR)
            assert sim.name == "SIMULATOR"
            assert sim.device_type == "rfid"
            assert sim.is_connected is False
            assert sim.is_reading is False

    @pytest.mark.asyncio
    async def test_sends_tags_and_increments(self):
        with patch("smartx_rfid.devices._base.on_event", Mock()):
            sim = SIMULATOR(send_interval=0.01)
            # capture events directly on instance
            sim.on_event = Mock()

            # mark connected and start reading
            sim.is_connected = True
            await sim.start_inventory()

            # allow a few tags to be emitted
            await asyncio.sleep(0.08)

            await sim.stop_inventory()

            # collect tag event calls
            calls = [c for c in sim.on_event.call_args_list if c[0][1] == "tag"]
            assert len(calls) >= 2

            first = calls[0][0][2]
            second = calls[1][0][2]

            epc1 = int(first["epc"], 16)
            epc2 = int(second["epc"], 16)
            tid1 = int(first["tid"], 16)
            tid2 = int(second["tid"], 16)

            assert epc2 == epc1 + 1
            assert tid2 == tid1 + 1
