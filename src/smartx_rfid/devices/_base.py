import asyncio
import logging
from datetime import datetime
from typing import Any, Optional, Callable

from smartx_rfid.utils.event import on_event


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
        # Event handler default (can be overridden per-device or by DeviceManager)
        # Signature: on_event(name: str, event_type: str, event_data=None)
        self.on_event: Callable[[str, str, Any], None] = on_event

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
        prev = getattr(self, "_connected_since", None)
        if prev is None:
            self._connected_since = datetime.now()
            try:
                self.emit_event("connection", True)
            except Exception:
                logging.exception("Error emitting connection=true event")

    def mark_disconnected(self) -> None:
        prev_conn = getattr(self, "_connected_since", None)
        prev_read = getattr(self, "_reading_since", None)
        # clear both connection and reading timestamps
        self._connected_since = None
        self._reading_since = None
        # emit reading off if it was active
        try:
            if prev_read is not None:
                self.emit_event("reading", False)
        except Exception:
            logging.exception("Error emitting reading=false event on disconnect")
        # emit connection off if previously connected
        try:
            if prev_conn is not None:
                self.emit_event("connection", False)
        except Exception:
            logging.exception("Error emitting connection=false event on disconnect")

    def mark_reading_start(self) -> None:
        # only record reading timestamp if connected
        if getattr(self, "_connected_since", None) is None:
            # not connected -> ignore
            return
        prev = getattr(self, "_reading_since", None)
        if prev is None:
            self._reading_since = datetime.now()
            try:
                self.emit_event("reading", True)
            except Exception:
                logging.exception("Error emitting reading=true event")

    def mark_reading_stop(self) -> None:
        prev = getattr(self, "_reading_since", None)
        if prev is not None:
            self._reading_since = None
            try:
                self.emit_event("reading", False)
            except Exception:
                logging.exception("Error emitting reading=false event")

    def emit_event(self, event_type: str, event_data: Any = None, *, name: Optional[str] = None) -> None:
        """Call the configured event handler safely.

        Defaults to `smartx_rfid.utils.event.on_event` if not overridden.
        """
        try:
            target_name = name or getattr(self, "name", None) or "UNKNOWN"
            if callable(self.on_event):
                self.on_event(target_name, event_type, event_data)
        except Exception as e:
            logging.error(f"Error in event handler for {getattr(self, 'name', None)}: {e}")

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
