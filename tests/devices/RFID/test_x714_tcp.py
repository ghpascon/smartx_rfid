import asyncio
import pytest

from smartx_rfid.devices.RFID.X714._main import X714


class FakeWriterClosing:
    def is_closing(self):
        return True


class FakeAsyncWriter:
    def __init__(self):
        self.closed = False

    def is_closing(self):
        return False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        await asyncio.sleep(0)


class FakeBlockingWriter:
    def __init__(self):
        self._event = asyncio.Event()
        self._buf = bytearray()

    def write(self, data: bytes):
        self._buf.extend(data)

    async def drain(self):
        # wait forever (until cancelled) to simulate a stalled drain
        await self._event.wait()

    def close(self):
        # simulate immediate close
        pass

    async def wait_closed(self):
        await asyncio.sleep(0)


class FakeFailingWriter:
    def __init__(self):
        self.closed = False

    def is_closing(self):
        return False

    def write(self, data: bytes):
        return None

    async def drain(self):
        raise ConnectionResetError("socket gone")

    def close(self):
        self.closed = True

    async def wait_closed(self):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_monitor_connection_detects_writer_closing():
    device = X714(connection_type="TCP")
    device.is_connected = True
    device.writer = FakeWriterClosing()
    device.reconnection_time = 0.01

    # run monitor_connection and wait for it to finish
    t = device.create_task(device.monitor_connection())
    await t

    assert device.is_connected is False
    assert device.is_reading is False


@pytest.mark.asyncio
async def test_close_cleans_up_writer_and_marks_disconnected():
    device = X714(connection_type="TCP")
    fake = FakeAsyncWriter()
    device.writer = fake
    device.reader = object()
    device.is_connected = True

    await device.close()

    assert device.is_connected is False
    assert fake.closed is True


@pytest.mark.asyncio
async def test_write_tcp_timeout_marks_disconnected():
    device = X714(connection_type="TCP")
    device.is_connected = True
    device.writer = FakeBlockingWriter()

    # call write_tcp and expect it to complete and mark device disconnected
    await device.write_tcp("ping", verbose=False)

    assert device.is_connected is False


@pytest.mark.asyncio
async def test_write_tcp_send_error_cleans_writer_state():
    device = X714(connection_type="TCP")
    fake = FakeFailingWriter()
    device.is_connected = True
    device.writer = fake
    device.reader = object()

    await device.write_tcp("ping", verbose=False)

    assert device.is_connected is False
    assert fake.closed is True
    assert device.writer is None
    assert device.reader is None
