"""Threading bridge between the blocking ShellClient and the Qt event loop."""

from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from ..client import ShellClient, ShellError
from ..config import ShellConfig


class _Bridge(QObject):
    done = pyqtSignal(int, object)
    failed = pyqtSignal(int, str, object)


Task = Callable[[], Any]


class ShellSession(QObject):
    """Owns one ShellClient, serialises nothing, delivers results on the GUI thread."""

    traces = pyqtSignal(dict)
    stateChanged = pyqtSignal(bool)
    busyChanged = pyqtSignal(int)

    def __init__(self, config: ShellConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.client = ShellClient(config, on_trace=self._on_trace)
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=f"ws-{config.id}")
        self._bridge = _Bridge()
        self._bridge.done.connect(self._dispatch_done)
        self._bridge.failed.connect(self._dispatch_failed)
        self._ok_handlers: dict[int, Callable[[Any], None]] = {}
        self._err_handlers: dict[int, Callable[[str], None]] = {}
        self._seq = 0
        self._inflight = 0
        self.connected = False
        self.last_error = ""
        self.latency_ms: float = 0.0
        self.info: dict[str, Any] = {}

    # ------------------------------------------------------------- internals
    def _on_trace(self, record: dict[str, Any]) -> None:
        self.latency_ms = record.get("elapsed", 0.0) * 1000.0
        self.traces.emit(record)

    def _dispatch_done(self, task_id: int, result: Any) -> None:
        handler = self._ok_handlers.pop(task_id, None)
        self._err_handlers.pop(task_id, None)
        self._inflight = max(0, self._inflight - 1)
        self.busyChanged.emit(self._inflight)
        if handler is not None:
            try:
                handler(result)
            except Exception:  # a UI bug must not kill the event loop
                traceback.print_exc()

    def _dispatch_failed(self, task_id: int, message: str, error: Any) -> None:
        handler = self._err_handlers.pop(task_id, None)
        self._ok_handlers.pop(task_id, None)
        self._inflight = max(0, self._inflight - 1)
        self.busyChanged.emit(self._inflight)
        self.last_error = message
        if handler is not None:
            try:
                handler(message)
            except Exception:
                traceback.print_exc()

    # ------------------------------------------------------------------- api
    def run_async(
        self,
        fn: Task,
        on_ok: Callable[[Any], None] | None = None,
        on_err: Callable[[str], None] | None = None,
    ) -> int:
        self._seq += 1
        task_id = self._seq
        if on_ok is not None:
            self._ok_handlers[task_id] = on_ok
        if on_err is not None:
            self._err_handlers[task_id] = on_err
        self._inflight += 1
        self.busyChanged.emit(self._inflight)

        def work() -> None:
            started = time.time()
            try:
                result = fn()
            except ShellError as exc:
                self._bridge.failed.emit(task_id, str(exc), exc)
            except Exception as exc:  # transport/codec/anything
                self._bridge.failed.emit(task_id, f"{type(exc).__name__}: {exc}", exc)
            else:
                elapsed = time.time() - started
                if isinstance(result, dict):
                    result.setdefault("_elapsed", elapsed)
                self._bridge.done.emit(task_id, result)

        self._pool.submit(work)
        return task_id

    def connect_shell(self, on_done: Callable[[dict[str, Any]], None], on_err: Callable[[str], None]) -> None:
        def ok(info: dict[str, Any]) -> None:
            self.connected = True
            self.info = info
            self.stateChanged.emit(True)
            on_done(info)

        def fail(message: str) -> None:
            self.connected = False
            self.stateChanged.emit(False)
            on_err(message)

        self.run_async(self.client.ping, ok, fail)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.client.close()

    @property
    def cwd(self) -> str:
        return self.client.config.cwd or self.info.get("cwd", "") or "/"

    @cwd.setter
    def cwd(self, value: str) -> None:
        self.client.config.cwd = value
