import asyncio
from datetime import datetime, timezone


class DeviceBase:
    """Mixin to track and cancel background asyncio Tasks for devices.

    Usage: inherit alongside existing base (multiple inheritance).
    - call DeviceBase.__init__(self) in subclass __init__
    - use self.create_task(coro) instead of asyncio.create_task
    - call await self.shutdown() to cancel/wait tasks
    """

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._running = True
        # connection / reading timestamps
        # Use timezone-aware datetimes (UTC)
        self._connected_since: datetime | None = None
        self._reading_since: datetime | None = None

    def create_task(self, coro: asyncio.coroutines):
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        self._tasks.add(task)

        def _on_done(t: asyncio.Task):
            try:
                self._tasks.discard(t)
            except Exception:
                pass

        task.add_done_callback(_on_done)
        return task

    def cancel_all(self):
        self._running = False
        for t in list(self._tasks):
            if not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass

    # -----------------------------
    # Connection / reading timestamp helpers
    # -----------------------------
    @property
    def connected_since(self) -> datetime | None:
        return getattr(self, "_connected_since", None)

    @property
    def reading_since(self) -> datetime | None:
        return getattr(self, "_reading_since", None)

    def mark_connected(self) -> None:
        self._connected_since = datetime.now(timezone.utc)

    def mark_disconnected(self) -> None:
        # clear both connection and reading timestamps
        self._connected_since = None
        self._reading_since = None

    def mark_reading_start(self) -> None:
        # only record reading timestamp if connected
        if getattr(self, "_connected_since", None) is None:
            # not connected -> ignore
            return
        self._reading_since = datetime.now(timezone.utc)

    def mark_reading_stop(self) -> None:
        self._reading_since = None

    @property
    def is_connected(self) -> bool:
        return getattr(self, "_connected_since", None) is not None

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        if value:
            self.mark_connected()
        else:
            self.mark_disconnected()

    @property
    def is_reading(self) -> bool:
        return getattr(self, "_reading_since", None) is not None

    @is_reading.setter
    def is_reading(self, value: bool) -> None:
        if value:
            self.mark_reading_start()
        else:
            self.mark_reading_stop()

    async def shutdown(self, timeout: float = 2.0):
        """Cancel and wait for outstanding tasks."""
        self._running = False
        tasks = [t for t in self._tasks if not t.done()]
        for t in tasks:
            try:
                t.cancel()
            except Exception:
                pass

        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                pass

    def __del__(self):
        # Best-effort cancellation when object is garbage-collected.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and not loop.is_closed():
            for t in list(self._tasks):
                try:
                    loop.call_soon_threadsafe(t.cancel)
                except Exception:
                    pass
